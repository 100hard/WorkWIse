import tkinter as tk
from tkinter import ttk, messagebox
import time
import win32gui
import cv2
import matplotlib.pyplot as plt
import numpy as np
import json
import os
from PIL import Image, ImageTk
import winsound

class ProductivityApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("WorkWise")
        self.root.geometry("800x600")  # Increased size for camera feed
        self.root.configure(bg="#f0f0f0")
        
        # Load or create app settings
        self.settings_file = "app_settings.json"
        self.load_settings()
        
        # Initialize variables
        self.timer_running = False
        self.start_time = 0
        self.distracted_time = 0
        self.check_interval = 1000  # Check every second
        self.camera_interval = 100  # Camera check interval (ms)
        
        # Focus mode variables
        self.focus_mode = False
        self.work_duration = 25 * 60  # 25 minutes in seconds
        self.break_duration = 5 * 60  # 5 minutes in seconds
        self.current_phase = "Work"
        self.phase_start_time = 0
        self.phase_time_left = self.work_duration
        self.consecutive_work_sessions = 0
        
        # Analytics data
        self.session_data = []
        self.unproductive_apps = set()
        self.app_usage_times = {}
        
        # Face detection setup
        self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        self.cap = None
        self.last_face_time = time.time()
        self.face_grace_period = 5  # seconds before marking as distracted
        
        # Create main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill="both", expand=True)
        
        # Left frame for timer and app management
        left_frame = ttk.Frame(main_frame)
        left_frame.pack(side="left", fill="both", expand=True)
        
        # Configure style
        style = ttk.Style()
        style.configure("TLabel", font=("Arial", 14))
        style.configure("TButton", font=("Arial", 12))
        
        # Create widgets in left frame
        self.time_label = ttk.Label(left_frame, text="Productive: 00:00:00\nDistracted: 00:00:00")
        self.time_label.pack(pady=10)
        
        # Status label
        self.status_label = ttk.Label(left_frame, text="Not Monitoring", foreground="gray")
        self.status_label.pack(pady=5)
        
        # Create buttons
        button_frame = ttk.Frame(left_frame)
        button_frame.pack(pady=10)
        
        self.start_button = ttk.Button(button_frame, text="Start Normal", command=self.start_timer)
        self.start_button.pack(side="left", padx=5)
        
        self.focus_button = ttk.Button(button_frame, text="Start Focus", command=self.start_focus_mode)
        self.focus_button.pack(side="left", padx=5)
        
        self.stop_button = ttk.Button(button_frame, text="Stop", command=self.stop_timer)
        self.stop_button.pack(side="left", padx=5)
        self.stop_button.state(['disabled'])
        
        # Create analytics button
        self.analytics_button = ttk.Button(button_frame, text="Show Analytics", command=self.show_analytics)
        self.analytics_button.pack(side="left", padx=5)
        
        # App management section
        app_frame = ttk.LabelFrame(left_frame, text="App Management", padding="10")
        app_frame.pack(fill="both", expand=True, pady=10)
        
        # App entry
        entry_frame = ttk.Frame(app_frame)
        entry_frame.pack(fill="x", pady=5)
        
        self.app_entry = ttk.Entry(entry_frame, width=30)
        self.app_entry.pack(side="left", padx=5)
        
        ttk.Button(entry_frame, text="Add to Unproductive", 
                  command=lambda: self.add_app(self.app_entry.get())).pack(side="left", padx=2)
        
        ttk.Button(entry_frame, text="Remove Selected", 
                  command=self.remove_selected_app).pack(side="left", padx=2)
        
        # App list with scrollbar
        list_frame = ttk.Frame(app_frame)
        list_frame.pack(fill="both", expand=True)
        
        ttk.Label(list_frame, text="Unproductive Apps (select to remove):").pack(anchor="w")
        
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")
        
        self.app_listbox = tk.Listbox(list_frame, height=5, width=40, selectmode="single")
        self.app_listbox.pack(side="left", fill="both", expand=True)
        
        scrollbar.config(command=self.app_listbox.yview)
        self.app_listbox.config(yscrollcommand=scrollbar.set)
        
        # Right frame for camera feed
        right_frame = ttk.Frame(main_frame)
        right_frame.pack(side="right", fill="both", expand=True, padx=10)
        
        self.camera_label = ttk.Label(right_frame, text="Initializing camera...")
        self.camera_label.pack(pady=10)
        
        self.camera_status = ttk.Label(right_frame, text="Face Detection: Not started", foreground="gray")
        self.camera_status.pack(pady=5)
        
        self.update_app_list()
    
    def load_settings(self):
        """Load app settings from JSON file"""
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r') as f:
                    settings = json.load(f)
                    self.unproductive_apps = set(settings.get('unproductive_apps', []))
            else:
                # Default settings
                self.unproductive_apps = set(['chrome', 'firefox', 'edge'])
                self.save_settings()
        except Exception as e:
            print(f"Error loading settings: {e}")
            self.unproductive_apps = set(['chrome', 'firefox', 'edge'])

    def save_settings(self):
        """Save app settings to JSON file"""
        try:
            settings = {
                'unproductive_apps': list(self.unproductive_apps)
            }
            with open(self.settings_file, 'w') as f:
                json.dump(settings, f, indent=4)
        except Exception as e:
            print(f"Error saving settings: {e}")

    def log_app_usage(self, window_title, duration):
        """Log duration of app usage, excluding WorkWise itself"""
        if window_title and "workwise" not in window_title:
            if window_title not in self.app_usage_times:
                self.app_usage_times[window_title] = 0
            self.app_usage_times[window_title] += duration

    def save_session_data(self):
        """Save current window data to session history"""
        if self.timer_running:
            try:
                window = win32gui.GetForegroundWindow()
                window_title = win32gui.GetWindowText(window).lower()
                if window_title and "workwise" not in window_title:  # Skip logging WorkWise itself
                    is_unproductive = any(app in window_title for app in self.unproductive_apps)
                    
                    self.session_data.append({
                        "time": time.time(),
                        "app": window_title,
                        "productive": not is_unproductive,
                        "unproductive": is_unproductive
                    })
                    
                    # Log app usage duration
                    self.log_app_usage(window_title, self.check_interval / 1000)
            except Exception as e:
                print(f"Error saving session data: {e}")

    def show_analytics(self):
        """Display session analytics"""
        if not self.session_data:
            messagebox.showinfo("Analytics", "Start a session first")
            return
        
        try:
            # Calculate basic stats
            total_time = time.time() - self.start_time
            unproductive_time = sum(1 for entry in self.session_data if entry["unproductive"]) * (self.check_interval / 1000)
            productive_time = total_time - unproductive_time
            
            # Get top apps by usage
            sorted_apps = sorted(self.app_usage_times.items(), key=lambda x: x[1], reverse=True)
            top_apps = sorted_apps[:3] if sorted_apps else []
            
            # Format analytics message
            analytics_msg = "Analytics\n\n"
            analytics_msg += f"Total Time: {self.format_time(total_time)}\n"
            analytics_msg += f"Productive Time: {self.format_time(productive_time)} ({productive_time/total_time*100:.1f}%)\n"
            analytics_msg += f"Unproductive Time: {self.format_time(unproductive_time)} ({unproductive_time/total_time*100:.1f}%)\n\n"
            
            analytics_msg += "Most Used Apps:\n"
            for app, duration in top_apps:
                analytics_msg += f"- {app}: {self.format_time(duration)}\n"
            
            # Show analytics in a custom dialog
            dialog = tk.Toplevel(self.root)
            dialog.title("WorkWise Analytics")
            dialog.geometry("400x500")
            dialog.transient(self.root)
            dialog.grab_set()
            
            # Add text widget with scrollbar
            text_frame = ttk.Frame(dialog)
            text_frame.pack(fill="both", expand=True, padx=10, pady=10)
            
            scrollbar = ttk.Scrollbar(text_frame)
            scrollbar.pack(side="right", fill="y")
            
            text_widget = tk.Text(text_frame, wrap="word", yscrollcommand=scrollbar.set)
            text_widget.pack(fill="both", expand=True)
            text_widget.insert("1.0", analytics_msg)
            text_widget.config(state="disabled")
            
            scrollbar.config(command=text_widget.yview)
            
            # Close button
            ttk.Button(dialog, text="Close", command=dialog.destroy).pack(pady=10)
            
        except Exception as e:
            messagebox.showerror("Error", f"Error showing analytics: {e}")

    def add_app(self, app_name):
        app_name = app_name.lower().strip()
        if app_name and app_name not in self.unproductive_apps:
            self.unproductive_apps.add(app_name)
            self.save_settings()
            self.update_app_list()
            self.app_entry.delete(0, tk.END)
            messagebox.showinfo("", f"Added '{app_name}' to unproductive apps")
    
    def remove_selected_app(self):
        selection = self.app_listbox.curselection()
        if selection:
            app_name = self.app_listbox.get(selection[0])
            if app_name in self.unproductive_apps:
                self.unproductive_apps.remove(app_name)
                self.save_settings()
                self.update_app_list()
                messagebox.showinfo("", f"Removed '{app_name}' from unproductive apps")
        else:
            messagebox.showwarning("", "Please select an app to remove")
    
    def remove_app(self, app_name):
        app_name = app_name.lower().strip()
        if app_name in self.unproductive_apps:
            self.unproductive_apps.remove(app_name)
            self.save_settings()
            self.update_app_list()
            self.app_entry.delete(0, tk.END)
            messagebox.showinfo("", f"Removed '{app_name}' from unproductive apps")
        else:
            messagebox.showwarning("", f"App '{app_name}' not found in the list")
    
    def update_app_list(self):
        self.app_listbox.delete(0, tk.END)
        for app in sorted(self.unproductive_apps):
            self.app_listbox.insert(tk.END, app)
    
    def start_timer(self):
        """Start timer and initialize session"""
        if not self.timer_running:
            self.cap = cv2.VideoCapture(0)
            if not self.cap.isOpened():
                messagebox.showerror("Error", "Could not open camera.")
                return
            
            # Reset session data
            self.session_data = []
            self.app_usage_times = {}
            self.start_time = time.time()
            self.last_face_time = time.time()
            self.distracted_time = 0
            self.timer_running = True
            
            # Update UI
            self.start_button.state(['disabled'])
            self.stop_button.state(['!disabled'])
            
            # Start monitoring
            self.update_camera()
            self.update_timer()
            self.check_active_window()
            self.save_session_data()  # Start logging session data

    def start_focus_mode(self):
        """Start Pomodoro focus mode with work/break intervals"""
        if not self.timer_running:
            self.cap = cv2.VideoCapture(0)
            if not self.cap.isOpened():
                messagebox.showerror("Error", "Could not open camera")
                return
            
            # Initialize focus mode
            self.focus_mode = True
            self.timer_running = True
            self.start_time = time.time()
            self.phase_start_time = time.time()
            self.phase_time_left = self.work_duration
            self.current_phase = "Work"
            self.distracted_time = 0
            self.consecutive_work_sessions = 0
            self.last_face_time = time.time()
            self.session_data = []
            self.app_usage_times = {}
            
            # Update UI
            self.start_button.state(['disabled'])
            self.focus_button.state(['disabled'])
            self.stop_button.state(['!disabled'])
            self.camera_label.config(text="Starting camera...")
            
            # Start monitoring - Important: Start camera update before showing dialog
            self.update_camera()
            self.check_active_window()
            self.update_focus_timer()
            self.save_session_data()
            
            # Play sound and show message
            winsound.Beep(800, 500)
            messagebox.showinfo("Focus Mode", "Work session started - Focus for 25 minutes")

    def update_timer(self):
        if self.timer_running:
            current_time = time.time()
            total_time = current_time - self.start_time
            productive_time = max(0, total_time - self.distracted_time)  # Ensure no negative time
            
            self.time_label.config(
                text=f"Productive: {self.format_time(productive_time)}\n"
                     f"Distracted: {self.format_time(self.distracted_time)}"
            )
            self.root.after(1000, self.update_timer)
    
    def update_focus_timer(self):
        """Update timer for focus mode"""
        if self.timer_running and self.focus_mode:
            current_time = time.time()
            elapsed = current_time - self.phase_start_time
            self.phase_time_left = (self.work_duration if self.current_phase == "Work" 
                                  else self.break_duration) - elapsed
            
            # Check if current phase is complete
            if self.phase_time_left <= 0:
                if self.current_phase == "Work":
                    self.consecutive_work_sessions += 1
                    if self.consecutive_work_sessions == 4:  # After 4 work sessions
                        self.current_phase = "Long Break"
                        self.phase_time_left = 15 * 60  # 15 minute break
                        winsound.Beep(1000, 800)
                        messagebox.showinfo("Long Break", 
                            "Great job! Take a 15-minute break")
                        self.consecutive_work_sessions = 0
                    else:
                        self.current_phase = "Break"
                        self.phase_time_left = self.break_duration
                        winsound.Beep(600, 500)
                        messagebox.showinfo("Break Time", 
                            "Good work! Take a 5-minute break")
                else:
                    self.current_phase = "Work"
                    self.phase_time_left = self.work_duration
                    winsound.Beep(800, 500)
                    messagebox.showinfo("Work Time", 
                        "Break over - Focus for 25 minutes")
                
                self.phase_start_time = time.time()
            
            # Update display
            if self.current_phase == "Work":
                productive_time = max(0, total_time - self.distracted_time)
                self.time_label.config(
                    text=f"Work Phase: {self.format_time(self.phase_time_left)}\n"
                         f"Productive: {self.format_time(productive_time)}\n"
                         f"Distracted: {self.format_time(self.distracted_time)}"
                )
            else:
                self.time_label.config(
                    text=f"{self.current_phase} Time: {self.format_time(self.phase_time_left)}\n"
                         f"Sessions Completed: {self.consecutive_work_sessions}"
                )
            
            self.root.after(1000, self.update_focus_timer)

    def check_active_window(self):
        """Monitor active window and update session data"""
        if self.timer_running:
            try:
                window = win32gui.GetForegroundWindow()
                window_title = win32gui.GetWindowText(window).lower()
                
                is_unproductive = any(app in window_title for app in self.unproductive_apps)
                
                if is_unproductive:
                    self.distracted_time += self.check_interval / 1000
                    self.status_label.config(text=f"Unproductive - {window_title}", foreground="red")
                    if self.focus_mode and self.current_phase == "Work":
                        winsound.Beep(300, 200)  # Warning beep
                else:
                    self.status_label.config(text=f"Productive - {window_title}", foreground="green")
                
                self.save_session_data()
                self.root.after(self.check_interval, self.check_active_window)
                
            except Exception as e:
                print(f"Error checking window: {e}")
                self.root.after(self.check_interval, self.check_active_window)
    
    def update_camera(self):
        """Update camera feed and face detection"""
        if self.timer_running and self.cap is not None:
            try:
                ret, frame = self.cap.read()
                if ret:
                    # Convert frame to grayscale for face detection
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    
                    # Detect faces with optimized parameters
                    faces = self.face_cascade.detectMultiScale(
                        gray,
                        scaleFactor=1.2,
                        minNeighbors=6,
                        minSize=(50, 50),
                        maxSize=(300, 300)
                    )
                    
                    # Draw rectangles around faces
                    for (x, y, w, h) in faces:
                        cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
                    
                    # Update face detection status
                    current_time = time.time()
                    if len(faces) > 0:
                        self.last_face_time = current_time
                        self.camera_status.config(text="Face Detection: Present", foreground="green")
                        if self.focus_mode and self.current_phase == "Break":
                            self.camera_status.config(text="On Break", foreground="blue")
                    else:
                        time_without_face = current_time - self.last_face_time
                        if time_without_face > 5:  # 5 seconds threshold
                            self.camera_status.config(text="Face Detection: Away!", foreground="red")
                            if self.focus_mode and self.current_phase == "Work":
                                winsound.Beep(300, 200)  # Warning beep
                    
                    # Convert frame for display
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    frame = cv2.resize(frame, (320, 240))  # Maintain consistent size
                    img = Image.fromarray(frame)
                    imgtk = ImageTk.PhotoImage(image=img)
                    self.camera_label.imgtk = imgtk
                    self.camera_label.config(image=imgtk, text="")
                
                # Schedule next update before any potential delays
                self.root.after(self.camera_interval, self.update_camera)
            except Exception as e:
                print(f"Camera error: {e}")
                self.camera_status.config(text=f"Camera Error: {str(e)}", foreground="red")
                self.root.after(self.camera_interval, self.update_camera)
    
    def stop_timer(self):
        """Stop timer and clean up"""
        self.timer_running = False
        self.focus_mode = False
        self.start_button.state(['!disabled'])
        self.focus_button.state(['!disabled'])
        self.stop_button.state(['disabled'])
        self.status_label.config(text="Not Monitoring", foreground="gray")
        self.camera_status.config(text="Face Detection: Stopped", foreground="gray")
        
        if self.cap is not None:
            self.cap.release()
            self.cap = None
    
    def format_time(self, seconds):
        total_minutes = int(seconds) // 60
        hours = total_minutes // 60
        minutes = total_minutes % 60
        remaining_seconds = int(seconds) % 60
        return f"{hours:02d}:{minutes:02d}:{remaining_seconds:02d}"
    
    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    app = ProductivityApp()
    app.run()
