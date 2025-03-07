import tkinter as tk
from tkinter import ttk, messagebox
from PIL import ImageGrab, Image, ImageTk  # Added ImageTk
import google.generativeai as genai
import base64
import io
import threading
from dotenv import load_dotenv
import os
import cv2
import mediapipe as mp
import math

load_dotenv()

class AImagine:
    def __init__(self, root):
        self.root = root
        self.root.title("AI-magine Board")
        self.root.geometry("1200x800")  # Increased window size
        
        # Gemini API setup
        self.GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
        genai.configure(api_key=self.GEMINI_API_KEY)
        self.model = genai.GenerativeModel('gemini-2.0-flash')
        
        # Drawing variables
        self.stroke_size = 2
        self.stroke_color = "white"
        self.last_x = None
        self.last_y = None
        self.undo_stack = []
        self.drawing = False
        
        # Camera control
        self.cam_running = False
        self.camera_paused = False
        self.current_frame = None  # To hold camera frames
        
        # UI Setup
        self.create_widgets()
        
        # Start camera thread
        self.start_camera()

    def create_widgets(self):
        # Main container
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Left panel (canvas)
        left_frame = ttk.Frame(main_frame, width=800)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Right panel (camera preview)
        right_frame = ttk.Frame(main_frame, width=400)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        # Header frame
        header_frame = ttk.Frame(left_frame)
        header_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Title
        ttk.Label(header_frame, text="AI-magine Board", font=('Arial', 14, 'bold')).pack(side=tk.LEFT)
        
        # Controls frame
        controls_frame = ttk.Frame(header_frame)
        controls_frame.pack(side=tk.RIGHT)
        
        # Stroke size control
        self.size_slider = ttk.Scale(controls_frame, from_=1, to=15, 
                                   command=lambda v: setattr(self, 'stroke_size', int(float(v))))
        self.size_slider.set(self.stroke_size)
        self.size_slider.pack(side=tk.LEFT, padx=5)
        
        # Tools
        tools_frame = ttk.Frame(controls_frame)
        tools_frame.pack(side=tk.LEFT)
        
        ttk.Button(tools_frame, text="✏️", command=lambda: setattr(self, 'stroke_color', 'white')).pack(side=tk.LEFT)
        ttk.Button(tools_frame, text="🧹", command=lambda: setattr(self, 'stroke_color', 'black')).pack(side=tk.LEFT)
        ttk.Button(tools_frame, text="↩️", command=self.undo).pack(side=tk.LEFT)
        
        # Action buttons
        ttk.Button(controls_frame, text="Calculate", command=self.analyze_canvas).pack(side=tk.LEFT, padx=5)
        ttk.Button(controls_frame, text="Reset", command=self.clear_canvas).pack(side=tk.LEFT)
        
        # Canvas
        self.canvas = tk.Canvas(left_frame, bg="black", bd=0, highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        # Camera preview
        self.camera_label = ttk.Label(right_frame)
        self.camera_label.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
        
        # Response label
        self.response_label = ttk.Label(left_frame, text="", wraplength=600)
        self.response_label.pack(side=tk.BOTTOM, fill=tk.X)

    def start_camera(self):
        self.cam_running = True
        self.hands = mp.solutions.hands.Hands()
        self.cap = cv2.VideoCapture(2)  # Changed to index 0 (default webcam)
        threading.Thread(target=self.hand_tracking_loop, daemon=True).start()

    def hand_tracking_loop(self):
        while self.cam_running:
            if not self.camera_paused:
                success, image = self.cap.read()
                if not success:
                    continue

                image = cv2.flip(image, 1)
                image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                results = self.hands.process(image_rgb)

                # Draw hand landmarks
                if results.multi_hand_landmarks:
                    for hand_landmarks in results.multi_hand_landmarks:
                        mp.solutions.drawing_utils.draw_landmarks(
                            image, hand_landmarks, mp.solutions.hands.HAND_CONNECTIONS)
                        self.process_gestures(hand_landmarks)

                # Update camera preview
                self.update_camera_preview(image)

    def update_camera_preview(self, frame):
        # Convert OpenCV frame to Tkinter image
        img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(img)
        img.thumbnail((400, 400))  # Resize for preview
        imgtk = ImageTk.PhotoImage(image=img)
        
        # Update label in main thread
        self.root.after(0, lambda: self._update_preview(imgtk))

    def _update_preview(self, image):
        self.camera_label.configure(image=image)
        self.camera_label.image = image  # Keep reference

    def process_gestures(self, landmarks):
        index_tip = landmarks.landmark[mp.solutions.hands.HandLandmark.INDEX_FINGER_TIP]
        thumb_tip = landmarks.landmark[mp.solutions.hands.HandLandmark.THUMB_TIP]
        
        distance = math.hypot(index_tip.x - thumb_tip.x, index_tip.y - thumb_tip.y)
        
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        x = int((1 - index_tip.x) * canvas_width)
        y = int(index_tip.y * canvas_height)

        if distance < 0.1:
            if not self.drawing:
                self.last_x, self.last_y = x, y
                self.drawing = True
            self.draw(x, y)
        else:
            self.drawing = False

    # Rest of the methods remain the same as before...
    # [Keep the draw, undo, analyze_canvas, clear_canvas, get_canvas_image, and on_close methods unchanged]
    def draw(self, x, y):
        if self.last_x and self.last_y:
            line = self.canvas.create_line(
                self.last_x, self.last_y, x, y,
                width=self.stroke_size, fill=self.stroke_color,
                capstyle=tk.ROUND, smooth=tk.TRUE
            )
            self.undo_stack.append(line)
        self.last_x = x
        self.last_y = y

    def undo(self):
        if self.undo_stack:
            item = self.undo_stack.pop()
            self.canvas.delete(item)

    def analyze_canvas(self):
        def run_analysis():
            try:
                self.camera_paused = True  # Pause camera during analysis
                base64_image = self.get_canvas_image()
                prompt = """Your name is AI-magine Board. Your task is to analyze the canvas and solve any given problem based on its type. Follow the specific rules and guidelines outlined below. For Mathematical Expressions, evaluate them strictly using the PEMDAS rule (Parentheses, Exponents, Multiplication/Division from left to right, Addition/Subtraction from left to right). For example, for 2 + 3 * 4, calculate it as 2 + (3 * 4) → 2 + 12 = 14. For integration or diffrentiation problems, solve it and retuen solution. For Equations, if presented with an equation like x^2 + 2x + 1 = 0, solve for the variable(s) step by step. For single-variable equations, provide the solution. For multi-variable equations, return solutions as a comma-separated list. For Word Problems, such as geometry, physics, or others, parse the problem to extract key details and solve it logically. Return the result with a very short explanation, including any necessary formulas or reasoning. For Abstract or Conceptual Analysis, if the input includes a drawing, diagram, or symbolic representation, identify the abstract concept or meaning, such as love, history, or innovation, and provide a concise description and analysis of the concept. For Creative or Contextual Questions, such as who made you or who is your creator, respond with Krish Patel made this app. Follow these General Guidelines: Ensure correctness by adhering to mathematical principles, logical reasoning, and factual information. Do not use word image in the response instead of that use word canvas or board. Return only the solution with a very short explanation. If no input is provided, respond with No Problem Provided!"""  # Use the same prompt as before
                
                response = self.model.generate_content([prompt, {"mime_type": "image/png", "data": base64_image}])
                self.response_label.config(text=response.text)
            finally:
                self.camera_paused = False  # Resume camera after analysis

        threading.Thread(target=run_analysis).start()

    def clear_canvas(self):
        self.canvas.delete("all")
        self.response_label.config(text="")

    def get_canvas_image(self):
        # Get canvas coordinates relative to screen
        x = self.root.winfo_rootx() + self.canvas.winfo_x()
        y = self.root.winfo_rooty() + self.canvas.winfo_y()
        x1 = x + self.canvas.winfo_width()
        y1 = y + self.canvas.winfo_height()

        # Capture screen area of the canvas
        img = ImageGrab.grab(bbox=(x, y, x1, y1))
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='PNG')
        return base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')

    def on_close(self):
        self.cam_running = False
        self.cap.release()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = AImagine(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()