import csv
import re
import os
import tkinter as tk
from tkinter import filedialog, messagebox, colorchooser
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

# ==========================================
# 1. THE PARSER (OSD -> CSV) [Optimized High-Res]
# ==========================================
def parse_walksnail_osd(input_file, cipher, speed_regex):
    base_name = os.path.splitext(input_file)[0]
    output_file = f"{base_name}.csv"
    
    log = []
    log.append(f">> Starting parser engine...")
    log.append(f">> Target: {os.path.basename(input_file)}")
    
    with open(input_file, 'r', encoding='cp1252', errors='ignore') as f:
        raw_data = f.read()

    log.append(f">> Read {len(raw_data):,} bytes of raw data")
    cleaned_data = raw_data.replace('\x00', '').replace('\r', ' ')
    
    log.append(">> Stripping null bytes & telemetry headers...")
    if "- - -" in cleaned_data and "S T A T S" in cleaned_data:
        cleaned_data = cleaned_data[:cleaned_data.find("- - -")]
    if "A R M E D" in cleaned_data:
        cleaned_data = cleaned_data[cleaned_data.rfind("A R M E D") + 9:]
    elif "BTFL" in cleaned_data:
        cleaned_data = cleaned_data[cleaned_data.rfind("BTFL") + 4:]

    frames = cleaned_data.split(cipher)[1:] 
    log.append(f">> Cipher isolated {len(frames):,} total OSD frames")

    headers = [
        "Flight Time", "Speed", "Altitude", "Vario Dir", "Vario Val", 
        "GPS Sats", "Link Quality", "Home Dist (ft)", "Flight Dist (ft)", 
        "Roll", "Pitch", "Flight Mode", "Rate Profile", "Throttle %", 
        "Bat Efficiency", "mAh Consumed", "Wattage", "Amps", "Voltage"
    ]

    csv_rows = []

    patterns = {
        'time': r'(\d{1,2}:\d{2}(?::\d{2})?)',
        'speed': speed_regex, 
        'altitude': r'\x7f[\s]*([\-\d\.\s]{1,15})\x0f',
        'vario': r'([uvw])[\s]*([\d\.\s]{1,15})™',
        'gps_sats': r'\x1f[\s]*([\d\s]{1,5})',
        'link_quality': r'\{[\s]*([\d\s]{1,4}:[\d\s]{1,4})',
        'home_dist': r'\x11[\s]*([-\w\.\s]{1,15})([\x0f~])',
        'flight_dist': r'q[\s]*([-\w\.\s]{1,15})([\x0f~])',
        'roll': r'\x14[\s]*([\-\d\.\s]{1,15})',
        'pitch': r'\x15[\s]*([\-\d\.\s]{1,15})',
        'throttle': r'\x04[\s]*([\d\s]{1,10})',
        'efficiency': r'([\-\d\s]{1,15})\x07[\s]*/',
        'mah': r'([\d\s]{1,15})\x07(?!\s*/)',
        'wattage': r'([\d\s]{1,15})W',
        'amps': r'([\-\d\.\s]{1,15})š',
        'voltage': r'([\d\.\s]{1,15})\x06'
    }

    compiled_patterns = {key: re.compile(pat) for key, pat in patterns.items()}

    log.append(">> Extracting aerodynamic variables at high resolution...")
    for frame in frames:
        def extract(key, group=1, default=""):
            match = compiled_patterns[key].search(frame)
            return match.group(group).replace(' ', '') if match else default
            
        def extract_dist(key):
            match = compiled_patterns[key].search(frame)
            if match:
                val_str = match.group(1).replace(' ', '')
                if match.group(2) == '~':
                    try: return str(round(float(val_str) * 5280.0, 1))
                    except ValueError: pass
                return val_str
            return ""

        flight_time = extract('time')
        row = [
            flight_time, extract('speed'), extract('altitude'), 
            extract('vario', 1), extract('vario', 2), extract('gps_sats'), 
            extract('link_quality'), extract_dist('home_dist'), 
            extract_dist('flight_dist'), extract('roll'), extract('pitch'), 
            "", "", extract('throttle'), extract('efficiency'), 
            extract('mah'), extract('wattage'), extract('amps'), extract('voltage')
        ]

        if sum(1 for item in row if item != "") >= 5 and flight_time:
            csv_rows.append(row)

    log.append(f">> Successfully yielded {len(csv_rows):,} high-resolution rows")
    if len(frames) > 0:
        log.append(f">> Frame validation yield: {(len(csv_rows)/len(frames))*100:.1f}%")
        
    log.append(">> File ready for analysis.")

    with open(output_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(csv_rows)
        
    return output_file, "\n".join(log)

# ==========================================
# 2. DATA ANALYSIS & GRAPHING LOGIC
# ==========================================
def analyze_data(filepath):
    speeds, amps, watts, altitudes, mahs, distances, throttles = [], [], [], [], [0], [0], []
    with open(filepath, 'r') as f:
        for row in csv.DictReader(f):
            try:
                speeds.append(float(row.get('Speed', 0) or 0))
                amp = float(row.get('Amps', 0) or 0)
                watt = float(row.get('Wattage', 0) or 0)
                if amp > 0: amps.append(amp)
                if watt > 0: watts.append(watt)
                altitudes.append(float(row.get('Altitude', 0) or 0))
                mahs.append(float(row.get('mAh Consumed', 0) or 0))
                distances.append(float(row.get('Flight Dist (ft)', 0) or 0))
                
                thr = float(row.get('Throttle %', 0) or 0)
                if thr > 0: throttles.append(thr)
            except ValueError: continue

    t_dist = max(distances)
    avg_spd = sum(speeds) / len(speeds) if speeds else 0
    avg_alt = sum(altitudes) / len(altitudes) if altitudes else 0
    
    return {
        "Total Flight Distance": t_dist,
        "Total mAh Consumed": max(mahs),
        "Efficiency (mAh/mile)": (max(mahs) / (t_dist / 5280)) if t_dist > 0 else 0,
        "Max Speed": max(speeds) if speeds else 0,
        "Overall Avg Speed": avg_spd,
        "Average Throttle": sum(throttles) / len(throttles) if throttles else 0,
        "Overall Avg Amps": sum(amps) / len(amps) if amps else 0,
        "Overall Avg Watts": sum(watts) / len(watts) if watts else 0,
        "Max Altitude": max(altitudes) if altitudes else 0,
        "Average Altitude": avg_alt,
        "Avg Altitude Variance": sum(abs(a - avg_alt) for a in altitudes) / len(altitudes) if altitudes else 0,
        "Overall Drag (W/Speed)": (sum(watts) / len(watts)) / avg_spd if (watts and avg_spd > 0) else 0
    }

def analyze_speed_tiers(filepath):
    tiers = {}
    with open(filepath, 'r') as f:
        for row in csv.DictReader(f):
            try:
                speed = float(row.get('Speed', 0) or 0)
                pitch = float(row.get('Pitch', 0) or 0)
                throttle = float(row.get('Throttle %', 0) or 0)
                watt = float(row.get('Wattage', 0) or 0)
                
                if speed >= 5 and watt > 0:
                    bucket = int(round(speed / 10.0) * 10)
                    if bucket not in tiers:
                        tiers[bucket] = {'p': [], 't': [], 'w': []}
                    tiers[bucket]['p'].append(pitch)
                    tiers[bucket]['t'].append(throttle)
                    tiers[bucket]['w'].append(watt)
            except ValueError: continue
            
    results = {}
    for b in sorted(tiers.keys()):
        vals = tiers[b]
        if len(vals['w']) >= 3: 
            results[b] = {
                'pitch': sum(vals['p']) / len(vals['p']),
                'throttle': sum(vals['t']) / len(vals['t']),
                'watt': sum(vals['w']) / len(vals['w'])
            }
    return results

def extract_plot_data(filepath):
    times, speeds, watts, altitudes, throttles = [], [], [], [], []
    with open(filepath, 'r') as f:
        for row in csv.DictReader(f):
            try:
                ts = row.get('Flight Time', '')
                if not ts or ':' not in ts: continue
                pts = ts.split(':')
                secs = int(pts[0])*60 + int(pts[1]) if len(pts)==2 else int(pts[0])*3600 + int(pts[1])*60 + int(pts[2])
                times.append(secs)
                speeds.append(float(row.get('Speed', 0) or 0))
                watts.append(float(row.get('Wattage', 0) or 0))
                altitudes.append(float(row.get('Altitude', 0) or 0))
                throttles.append(float(row.get('Throttle %', 0) or 0))
            except ValueError: continue
    return times, speeds, watts, altitudes, throttles

# ==========================================
# 3. GRAPHICAL DASHBOARD (TKINTER)
# ==========================================
class FlightDashboard(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Walksnail Flight Analyzer V.2")
        self.geometry("1500x950")
        
        try:
            self.iconbitmap("icon.ico")
        except Exception:
            pass

        self.file1 = None
        self.file2 = None
        self.osd1_path = None
        self.osd2_path = None
        
        self.current_craft1 = ""
        self.current_craft2 = ""
        
        self.cipher_var = tk.StringVar(value="œ")
        self.speed_regex_var = tk.StringVar(value=r"p[\s]*([\d\.\s]{1,15})(?:\x9d)?")
        self.craft_regex_var = tk.StringVar(value=r"([A-Za-z0-9][A-Za-z0-9_ \"\'\-\.]*?)\s{5,}$")
        
        self.color1 = tk.StringVar(value="#1f77b4")
        self.color2 = tk.StringVar(value="#ff7f0e")
        self.sync_name1_var = tk.BooleanVar(value=False)
        self.sync_name2_var = tk.BooleanVar(value=False)
        
        # --- NATIVE MENU BAR SETUP ---
        menubar = tk.Menu(self)
        self.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Load Flight 1 OSD...", command=self.load_file1)
        file_menu.add_command(label="Load Flight 2 OSD...", command=self.load_file2)
        file_menu.add_separator()
        file_menu.add_command(label="Analyze & Generate Dashboard", command=self.run_analysis)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.quit)
        menubar.add_cascade(label="File", menu=file_menu)

        tools_menu = tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(label="Raw Data Inspector (Flight 1)", command=lambda: self.open_debug_window(1))
        tools_menu.add_command(label="Raw Data Inspector (Flight 2)", command=lambda: self.open_debug_window(2))
        menubar.add_cascade(label="Tools", menu=tools_menu)

        settings_menu = tk.Menu(menubar, tearoff=0)
        settings_menu.add_command(label="Parser Rules...", command=self.open_settings_window)
        menubar.add_cascade(label="Settings", menu=settings_menu)
        
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="About", command=self.open_about_window)
        menubar.add_cascade(label="Help", menu=help_menu)
        
        # --- SLIM QUICK-ACCESS TOOLBAR ---
        toolbar = tk.Frame(self, padx=10, pady=8, bg="#e9ecef", bd=1, relief=tk.RAISED)
        toolbar.pack(fill=tk.X)

        def choose_color1():
            color = colorchooser.askcolor(title="Choose color for Flight 1", initialcolor=self.color1.get())[1]
            if color:
                self.color1.set(color)
                self.btn_c1.config(fg=color)

        def choose_color2():
            color = colorchooser.askcolor(title="Choose color for Flight 2", initialcolor=self.color2.get())[1]
            if color:
                self.color2.set(color)
                self.btn_c2.config(fg=color)

        tk.Button(toolbar, text="▶ ANALYZE", bg="#2a9d8f", fg="white", font=("Arial", 9, "bold"), cursor="hand2", command=self.run_analysis, padx=12).pack(side=tk.LEFT, padx=(0, 4))
        tk.Button(toolbar, text="CLEAR", bg="#e76f51", fg="white", font=("Arial", 9, "bold"), cursor="hand2", command=self.clear_all, padx=10).pack(side=tk.LEFT, padx=(0, 10))
        
        tk.Frame(toolbar, width=2, bg="gray").pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=2)

        tk.Label(toolbar, text="Flight 1:", font=("Arial", 10, "bold"), bg="#e9ecef").pack(side=tk.LEFT, padx=(5,2))
        self.name1 = tk.Entry(toolbar, width=12)
        self.name1.insert(0, "Flight 1")
        self.name1.pack(side=tk.LEFT, padx=2)
        
        self.chk_sync1 = tk.Checkbutton(toolbar, text="Sync", variable=self.sync_name1_var, command=self.toggle_sync1, bg="#e9ecef", font=("Arial", 8))
        self.chk_sync1.pack(side=tk.LEFT, padx=(0, 2))
        
        self.btn_c1 = tk.Button(toolbar, text="■", fg=self.color1.get(), font=("Arial", 14), relief=tk.FLAT, bg="#e9ecef", activebackground="#e9ecef", cursor="hand2", command=choose_color1)
        self.btn_c1.pack(side=tk.LEFT, padx=2)
        
        self.lbl_f1 = tk.Label(toolbar, text="[No file loaded]", bg="#e9ecef", fg="gray", font=("Arial", 9, "italic"))
        self.lbl_f1.pack(side=tk.LEFT, padx=(2, 5))
        
        self.craft_lbl_f1 = tk.Label(toolbar, text="", bg="#e9ecef", fg="#2a9d8f", font=("Arial", 9, "bold"))
        self.craft_lbl_f1.pack(side=tk.LEFT, padx=(0, 5))
        
        tk.Button(toolbar, text="🔍 Debug", font=("Arial", 8), command=lambda: self.open_debug_window(1)).pack(side=tk.LEFT, padx=(0, 10))
        
        tk.Frame(toolbar, width=2, bg="gray").pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=2)
        
        tk.Label(toolbar, text="Flight 2:", font=("Arial", 10, "bold"), bg="#e9ecef").pack(side=tk.LEFT, padx=(15,2))
        self.name2 = tk.Entry(toolbar, width=12)
        self.name2.insert(0, "Flight 2")
        self.name2.pack(side=tk.LEFT, padx=2)
        
        self.chk_sync2 = tk.Checkbutton(toolbar, text="Sync", variable=self.sync_name2_var, command=self.toggle_sync2, bg="#e9ecef", font=("Arial", 8))
        self.chk_sync2.pack(side=tk.LEFT, padx=(0, 2))
        
        self.btn_c2 = tk.Button(toolbar, text="■", fg=self.color2.get(), font=("Arial", 14), relief=tk.FLAT, bg="#e9ecef", activebackground="#e9ecef", cursor="hand2", command=choose_color2)
        self.btn_c2.pack(side=tk.LEFT, padx=2)
        
        self.lbl_f2 = tk.Label(toolbar, text="[No file loaded]", bg="#e9ecef", fg="gray", font=("Arial", 9, "italic"))
        self.lbl_f2.pack(side=tk.LEFT, padx=(2, 5))
        
        self.craft_lbl_f2 = tk.Label(toolbar, text="", bg="#e9ecef", fg="#2a9d8f", font=("Arial", 9, "bold"))
        self.craft_lbl_f2.pack(side=tk.LEFT, padx=(0, 5))

        tk.Button(toolbar, text="🔍 Debug", font=("Arial", 8), command=lambda: self.open_debug_window(2)).pack(side=tk.LEFT, padx=(0, 10))

        # --- BOTTOM TASKBAR (Status Bar) ---
        self.status_frame = tk.Frame(self, bg="#e9ecef", bd=1, relief=tk.RAISED, padx=10, pady=6)
        self.status_frame.pack(side=tk.BOTTOM, fill=tk.X)
        tk.Label(self.status_frame, text="Ready. Load two flights via the File menu to calculate performance verdicts.", bg="#e9ecef", fg="gray", font=("Arial", 10, "italic")).pack(side=tk.LEFT)

        # --- MAIN SPLIT LAYOUT (50/50) ---
        main_pane = tk.PanedWindow(self, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.left_pane = tk.Frame(main_pane, bg="#f8f9fa")
        main_pane.add(self.left_pane, width=730) 
        
        self.plot_frame = tk.Frame(main_pane, bg="white")
        main_pane.add(self.plot_frame)

        self.console_frame = tk.Frame(self.left_pane, bg="#f8f9fa")
        self.console_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        lbl_frame = tk.Frame(self.console_frame, bg="#f8f9fa")
        lbl_frame.pack(fill=tk.X, pady=(0,2))
        tk.Label(lbl_frame, text="Flight 1 Output", font=("Arial", 9, "bold"), fg="gray", bg="#f8f9fa").pack(side=tk.LEFT, padx=5)
        tk.Label(lbl_frame, text="Flight 2 Output", font=("Arial", 9, "bold"), fg="gray", bg="#f8f9fa").pack(side=tk.RIGHT, padx=5)
        
        txt_container = tk.Frame(self.console_frame, bg="#f8f9fa")
        txt_container.pack(fill=tk.X)
        txt_container.columnconfigure(0, weight=1)
        txt_container.columnconfigure(1, weight=1)
        
        self.txt_log1 = tk.Text(txt_container, height=6, font=("Consolas", 8), bg="#1e1e1e", fg="#4af626", bd=2, relief=tk.SUNKEN)
        self.txt_log1.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.txt_log1.insert(tk.END, ">> Awaiting Flight 1 OSD...")
        self.txt_log1.config(state=tk.DISABLED)
        
        self.txt_log2 = tk.Text(txt_container, height=6, font=("Consolas", 8), bg="#1e1e1e", fg="#4af626", bd=2, relief=tk.SUNKEN)
        self.txt_log2.grid(row=0, column=1, sticky="ew", padx=(5, 0))
        self.txt_log2.insert(tk.END, ">> Awaiting Flight 2 OSD...")
        self.txt_log2.config(state=tk.DISABLED)

        # --- SCROLLABLE TABLE CONTAINER ---
        table_container = tk.Frame(self.left_pane, bg="#f8f9fa")
        table_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        
        self.canvas = tk.Canvas(table_container, bg="#f8f9fa", highlightthickness=0)
        self.scrollbar = tk.Scrollbar(table_container, orient="vertical", command=self.canvas.yview)
        
        self.table_frame = tk.Frame(self.canvas, bg="#f8f9fa", relief=tk.SUNKEN, borderwidth=1)
        
        self.table_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        self.canvas_window = self.canvas.create_window((0, 0), window=self.table_frame, anchor="nw")
        
        def on_canvas_configure(e):
            self.canvas.itemconfig(self.canvas_window, width=e.width)
        self.canvas.bind("<Configure>", on_canvas_configure)
        
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        
        def _on_mousewheel(event):
            self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        self.canvas.bind_all("<MouseWheel>", _on_mousewheel)

    def clear_all(self):
        self.file1 = None
        self.file2 = None
        self.osd1_path = None
        self.osd2_path = None
        self.current_craft1 = ""
        self.current_craft2 = ""
        
        self.name1.delete(0, tk.END)
        self.name1.insert(0, "Flight 1")
        self.sync_name1_var.set(False)
        
        self.name2.delete(0, tk.END)
        self.name2.insert(0, "Flight 2")
        self.sync_name2_var.set(False)
        
        self.lbl_f1.config(text="[No file loaded]", fg="gray", font=("Arial", 9, "italic"))
        self.craft_lbl_f1.config(text="")
        
        self.lbl_f2.config(text="[No file loaded]", fg="gray", font=("Arial", 9, "italic"))
        self.craft_lbl_f2.config(text="")
        
        self.txt_log1.config(state=tk.NORMAL)
        self.txt_log1.delete(1.0, tk.END)
        self.txt_log1.insert(tk.END, ">> Awaiting Flight 1 OSD...")
        self.txt_log1.config(state=tk.DISABLED)
        
        self.txt_log2.config(state=tk.NORMAL)
        self.txt_log2.delete(1.0, tk.END)
        self.txt_log2.insert(tk.END, ">> Awaiting Flight 2 OSD...")
        self.txt_log2.config(state=tk.DISABLED)
        
        for widget in self.table_frame.winfo_children():
            widget.destroy()
            
        for widget in self.status_frame.winfo_children():
            widget.destroy()
        tk.Label(self.status_frame, text="Ready. Load two flights via the File menu to calculate performance summary.", bg="#e9ecef", fg="gray", font=("Arial", 10, "italic")).pack(side=tk.LEFT)
        
        for widget in self.plot_frame.winfo_children():
            widget.destroy()

    def toggle_sync1(self):
        if self.sync_name1_var.get() and self.current_craft1:
            self.name1.delete(0, tk.END)
            self.name1.insert(0, self.current_craft1)

    def toggle_sync2(self):
        if self.sync_name2_var.get() and self.current_craft2:
            self.name2.delete(0, tk.END)
            self.name2.insert(0, self.current_craft2)

    def open_settings_window(self):
        settings_win = tk.Toplevel(self)
        settings_win.title("Parser Settings")
        settings_win.geometry("500x200")
        settings_win.grab_set() 
        
        pad_frame = tk.Frame(settings_win, padx=20, pady=20)
        pad_frame.pack(fill=tk.BOTH, expand=True)
        
        tk.Label(pad_frame, text="OSD Frame Cipher:", font=("Arial", 10, "bold")).grid(row=0, column=0, sticky="w", pady=5)
        tk.Entry(pad_frame, textvariable=self.cipher_var, width=10, font=("Consolas", 10)).grid(row=0, column=1, sticky="w", padx=10)
        
        tk.Label(pad_frame, text="Speed Regex:", font=("Arial", 10, "bold")).grid(row=1, column=0, sticky="w", pady=10)
        tk.Entry(pad_frame, textvariable=self.speed_regex_var, width=35, font=("Consolas", 10)).grid(row=1, column=1, sticky="w", padx=10)
        
        tk.Label(pad_frame, text="Craft Name Regex:", font=("Arial", 10, "bold")).grid(row=2, column=0, sticky="w", pady=10)
        tk.Entry(pad_frame, textvariable=self.craft_regex_var, width=35, font=("Consolas", 10)).grid(row=2, column=1, sticky="w", padx=10)
        
        tk.Label(pad_frame, text="(Changes will apply on next file load)", fg="gray", font=("Arial", 9)).grid(row=3, column=0, columnspan=2, pady=10)

    def open_about_window(self):
        about_win = tk.Toplevel(self)
        about_win.title("About Walksnail Flight Analyzer")
        about_win.geometry("500x450")
        about_win.grab_set()
        
        content_frame = tk.Frame(about_win, padx=15, pady=15, bg="#f0f0f0")
        content_frame.pack(fill=tk.BOTH, expand=True)
        
        try:
            from PIL import Image, ImageTk
            if os.path.exists("icon.png"):
                pil_img = Image.open("icon.png")
                pil_img = pil_img.resize((128, 128), Image.Resampling.LANCZOS)
                self.about_logo = ImageTk.PhotoImage(pil_img)
                logo_label = tk.Label(content_frame, image=self.about_logo, bg="#f0f0f0")
                logo_label.pack(pady=(0, 10))
        except Exception:
            pass 
            
        txt_frame = tk.Frame(content_frame, bg="#f0f0f0")
        txt_frame.pack(fill=tk.BOTH, expand=True)
        
        txt = tk.Text(txt_frame, wrap="word", font=("Arial", 10), bg="#f0f0f0", fg="#222222", relief=tk.FLAT, borderwidth=0, highlightthickness=0, padx=5, pady=5)
        scroll = tk.Scrollbar(txt_frame, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=scroll.set)
        
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        content = "Walksnail Flight Analyzer\nHigh-resolution OSD parsing and aerodynamic comparison dashboard."
        try:
            if os.path.exists("about.fa2"):
                with open("about.fa2", "r", encoding="utf-8") as f:
                    content = f.read()
        except Exception as e:
            content = f"Error reading about: {str(e)}"
            
        txt.insert(tk.END, content)
        txt.config(state=tk.DISABLED)
        
        btn_frame = tk.Frame(content_frame, bg="#f0f0f0", pady=10)
        btn_frame.pack(fill=tk.X)
        tk.Button(btn_frame, text="OK", width=10, command=about_win.destroy, relief=tk.RAISED).pack()

    def open_debug_window(self, flight_num):
        path = self.osd1_path if flight_num == 1 else self.osd2_path
        if not path:
            messagebox.showinfo("Error", f"Please load an OSD file for Flight {flight_num} first.")
            return
            
        debug_win = tk.Toplevel(self)
        debug_win.title(f"Raw Data Inspector - Flight {flight_num} ({os.path.basename(path)})")
        debug_win.geometry("900x700")
        
        txt = tk.Text(debug_win, wrap="word", font=("Consolas", 11), bg="#1e1e1e", fg="#d4d4d4", padx=10, pady=10)
        scroll = tk.Scrollbar(debug_win, command=txt.yview)
        txt.configure(yscrollcommand=scroll.set)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        try:
            with open(path, 'r', encoding='cp1252', errors='ignore') as f:
                raw_data = f.read()
                
            cleaned_data = raw_data.replace('\x00', '').replace('\r', ' ')
            if "- - -" in cleaned_data and "S T A T S" in cleaned_data:
                cleaned_data = cleaned_data[:cleaned_data.find("- - -")]
            if "A R M E D" in cleaned_data:
                cleaned_data = cleaned_data[cleaned_data.rfind("A R M E D") + 9:]
            elif "BTFL" in cleaned_data:
                cleaned_data = cleaned_data[cleaned_data.rfind("BTFL") + 4:]
                
            frames = cleaned_data.split(self.cipher_var.get())[:50] 
            
            txt.insert(tk.END, "=== RAW OSD STRING PREVIEW (First 50 Frames) ===\n")
            for i, frame in enumerate(frames):
                txt.insert(tk.END, f"--- FRAME {i} ---\n", "header")
                txt.insert(tk.END, repr(frame) + "\n\n", "code")
                
            txt.tag_config("header", foreground="#569cd6", font=("Consolas", 11, "bold"))
            txt.tag_config("code", foreground="#ce9178")
            txt.config(state=tk.DISABLED)
        except Exception as e:
            txt.insert(tk.END, f"Error reading file: {str(e)}")

    def get_craft_name(self, filepath, cipher, regex):
        if not regex: return "Unknown"
        try:
            with open(filepath, 'r', encoding='cp1252', errors='ignore') as f:
                raw_data = f.read()
            cleaned_data = raw_data.replace('\x00', '').replace('\r', ' ')
            if "- - -" in cleaned_data and "S T A T S" in cleaned_data:
                cleaned_data = cleaned_data[:cleaned_data.find("- - -")]
            if "A R M E D" in cleaned_data:
                cleaned_data = cleaned_data[cleaned_data.rfind("A R M E D") + 9:]
            elif "BTFL" in cleaned_data:
                cleaned_data = cleaned_data[cleaned_data.rfind("BTFL") + 4:]
            frames = cleaned_data.split(cipher)
            if len(frames) > 0:
                match = re.search(regex, frames[0])
                if match:
                    craft = match.group(1).strip()
                    if craft: return craft
        except Exception:
            pass
        return "Unknown"

    def load_file1(self):
        f = filedialog.askopenfilename(filetypes=[("OSD Files", "*.osd")])
        if f:
            self.osd1_path = f
            self.lbl_f1.config(text=os.path.basename(f), fg="black", font=("Arial", 9, "bold"))
            craft = self.get_craft_name(f, self.cipher_var.get(), self.craft_regex_var.get())
            if craft != "Unknown":
                self.current_craft1 = craft
                self.craft_lbl_f1.config(text=f"[{craft}]")
                if self.sync_name1_var.get():
                    self.name1.delete(0, tk.END)
                    self.name1.insert(0, craft)
            else:
                self.current_craft1 = ""
                self.craft_lbl_f1.config(text="")
                
            output_file, log_str = parse_walksnail_osd(f, self.cipher_var.get(), self.speed_regex_var.get())
            self.file1 = output_file
            
            self.txt_log1.config(state=tk.NORMAL)
            self.txt_log1.delete(1.0, tk.END)
            self.txt_log1.insert(tk.END, log_str)
            self.txt_log1.config(state=tk.DISABLED)

    def load_file2(self):
        f = filedialog.askopenfilename(filetypes=[("OSD Files", "*.osd")])
        if f:
            self.osd2_path = f
            self.lbl_f2.config(text=os.path.basename(f), fg="black", font=("Arial", 9, "bold"))
            craft = self.get_craft_name(f, self.cipher_var.get(), self.craft_regex_var.get())
            if craft != "Unknown":
                self.current_craft2 = craft
                self.craft_lbl_f2.config(text=f"[{craft}]")
                if self.sync_name2_var.get():
                    self.name2.delete(0, tk.END)
                    self.name2.insert(0, craft)
            else:
                self.current_craft2 = ""
                self.craft_lbl_f2.config(text="")
                
            output_file, log_str = parse_walksnail_osd(f, self.cipher_var.get(), self.speed_regex_var.get())
            self.file2 = output_file
            
            self.txt_log2.config(state=tk.NORMAL)
            self.txt_log2.delete(1.0, tk.END)
            self.txt_log2.insert(tk.END, log_str)
            self.txt_log2.config(state=tk.DISABLED)

    def run_analysis(self):
        if not self.file1 or not self.file2:
            messagebox.showwarning("Missing Files", "Please select two OSD files via the File menu first.")
            return
            
        n1, n2 = self.name1.get(), self.name2.get()
        c1, c2 = self.color1.get(), self.color2.get()
        d1, d2 = analyze_data(self.file1), analyze_data(self.file2)
        
        tiers1 = analyze_speed_tiers(self.file1)
        tiers2 = analyze_speed_tiers(self.file2)
        
        def get_best_cruise(tiers):
            best_speed = 0
            min_drag = float('inf')
            for b, data in tiers.items():
                if b > 0 and data['watt'] > 0:
                    drag = data['watt'] / b
                    if drag < min_drag:
                        min_drag = drag
                        best_speed = b
            return best_speed

        best_cruise1 = get_best_cruise(tiers1)
        best_cruise2 = get_best_cruise(tiers2)
        
        for widget in self.status_frame.winfo_children():
            widget.destroy()
            
        def get_winner(val1, val2, name1, name2, col1, col2, lower_is_better=True):
            if val1 == 0 and val2 == 0: return ("N/A", "black")
            if val1 == val2: return ("Tie", "black")
            if lower_is_better:
                return (name1, col1) if val1 < val2 else (name2, col2)
            else:
                return (name1, col1) if val1 > val2 else (name2, col2)
                
        eff_win, eff_col = get_winner(d1["Efficiency (mAh/mile)"], d2["Efficiency (mAh/mile)"], n1, n2, c1, c2, True)
        drag_win, drag_col = get_winner(d1["Overall Drag (W/Speed)"], d2["Overall Drag (W/Speed)"], n1, n2, c1, c2, True)
        spd_win, spd_col = get_winner(d1["Max Speed"], d2["Max Speed"], n1, n2, c1, c2, False)

        tk.Label(self.status_frame, text="FLIGHT COMPARISON SUMMARY:", font=("Arial", 10, "bold"), bg="#e9ecef").pack(side=tk.LEFT, padx=(5, 15))
        tk.Label(self.status_frame, text="🏆 Most Efficient: ", font=("Arial", 10), bg="#e9ecef").pack(side=tk.LEFT)
        tk.Label(self.status_frame, text=eff_win, font=("Arial", 10, "bold"), fg=eff_col, bg="#e9ecef").pack(side=tk.LEFT)
        tk.Label(self.status_frame, text="   |   ", font=("Arial", 10), bg="#e9ecef").pack(side=tk.LEFT)
        tk.Label(self.status_frame, text="💨 Least Overall Drag: ", font=("Arial", 10), bg="#e9ecef").pack(side=tk.LEFT)
        tk.Label(self.status_frame, text=drag_win, font=("Arial", 10, "bold"), fg=drag_col, bg="#e9ecef").pack(side=tk.LEFT)
        tk.Label(self.status_frame, text="   |   ", font=("Arial", 10), bg="#e9ecef").pack(side=tk.LEFT)
        tk.Label(self.status_frame, text="🚀 Highest Top Speed: ", font=("Arial", 10), bg="#e9ecef").pack(side=tk.LEFT)
        tk.Label(self.status_frame, text=spd_win, font=("Arial", 10, "bold"), fg=spd_col, bg="#e9ecef").pack(side=tk.LEFT)

        for widget in self.table_frame.winfo_children():
            widget.destroy()

        padding_y = 3
        tk.Label(self.table_frame, text="Metric", font=("Arial", 11, "bold"), bg="#f8f9fa", anchor="w").grid(row=0, column=0, sticky="w", pady=(5, 10))
        tk.Label(self.table_frame, text=n1, font=("Arial", 11, "bold"), bg="#f8f9fa", anchor="e", fg=c1).grid(row=0, column=1, sticky="e", padx=15, pady=(5, 10))
        tk.Label(self.table_frame, text=n2, font=("Arial", 11, "bold"), bg="#f8f9fa", anchor="e", fg=c2).grid(row=0, column=2, sticky="e", padx=15, pady=(5, 10))
        
        metrics = [
            ("Total Flight Distance", "{:.0f} ft"),
            ("Total mAh Consumed", "{:.0f} mAh"),
            ("Efficiency (mAh/mile)", "{:.0f} mAh/mi"),
            ("Max Speed", "{:.1f} mph"),
            ("Overall Avg Speed", "{:.1f} mph"),
            ("Average Throttle", "{:.1f} %"),
            ("Overall Avg Amps", "{:.2f} A"),
            ("Overall Avg Watts", "{:.0f} W"),
            ("Max Altitude", "{:.1f} ft"),
            ("Average Altitude", "{:.1f} ft"),
            ("Avg Altitude Variance", "{:.1f} ft off avg"),
            ("Overall Drag (W/Speed)", "{:.2f} W per mph")
        ]
        
        row_idx = 1
        for key, fmt in metrics:
            tk.Label(self.table_frame, text=key, font=("Arial", 10, "bold"), bg="#f8f9fa", anchor="w").grid(row=row_idx, column=0, sticky="w", pady=padding_y)
            tk.Label(self.table_frame, text=fmt.format(d1[key]), font=("Consolas", 10), bg="#f8f9fa").grid(row=row_idx, column=1, sticky="e", padx=15, pady=padding_y)
            tk.Label(self.table_frame, text=fmt.format(d2[key]), font=("Consolas", 10), bg="#f8f9fa").grid(row=row_idx, column=2, sticky="e", padx=15, pady=padding_y)
            row_idx += 1
            
        # RESTORED: Attitude by Speed Tier section
        tk.Frame(self.table_frame, height=2, bd=1, relief=tk.SUNKEN, bg="gray").grid(row=row_idx, column=0, columnspan=3, sticky="we", pady=8)
        row_idx += 1
        
        tk.Label(self.table_frame, text="Attitude by Speed Tier", font=("Arial", 11, "bold"), bg="#f8f9fa", anchor="w").grid(row=row_idx, column=0, sticky="w", pady=(0, 5))
        row_idx += 1
        
        all_buckets = sorted(set(list(tiers1.keys()) + list(tiers2.keys())))
        
        for b in all_buckets:
            tk.Label(self.table_frame, text=f"{b} mph", font=("Arial", 10, "bold"), bg="#f8f9fa", anchor="w").grid(row=row_idx, column=0, sticky="w", pady=1)
            
            if b in tiers1:
                t1_data = tiers1[b]
                txt1 = f"{t1_data['pitch']:.1f}° pitch, {t1_data['throttle']:.0f}% thr, {t1_data['watt']:.0f} W"
            else:
                txt1 = "N/A"
                
            if b in tiers2:
                t2_data = tiers2[b]
                txt2 = f"{t2_data['pitch']:.1f}° pitch, {t2_data['throttle']:.0f}% thr, {t2_data['watt']:.0f} W"
            else:
                txt2 = "N/A"
                
            tk.Label(self.table_frame, text=txt1, font=("Consolas", 9), bg="#f8f9fa").grid(row=row_idx, column=1, sticky="e", padx=15, pady=1)
            tk.Label(self.table_frame, text=txt2, font=("Consolas", 9), bg="#f8f9fa").grid(row=row_idx, column=2, sticky="e", padx=15, pady=1)
            row_idx += 1

        # RESTORED: Drag Profile by Tier section
        tk.Frame(self.table_frame, height=2, bd=1, relief=tk.SUNKEN, bg="gray").grid(row=row_idx, column=0, columnspan=3, sticky="we", pady=8)
        row_idx += 1
        
        tk.Label(self.table_frame, text="Drag Profile (W/mph) by Tier", font=("Arial", 11, "bold"), bg="#f8f9fa", anchor="w").grid(row=row_idx, column=0, sticky="w", pady=(0, 5))
        row_idx += 1
        
        for b in all_buckets:
            if b == 0: continue 
            
            tk.Label(self.table_frame, text=f"{b} mph", font=("Arial", 10, "bold"), bg="#f8f9fa", anchor="w").grid(row=row_idx, column=0, sticky="w", pady=1)
            
            drag1 = (tiers1[b]['watt'] / b) if b in tiers1 else None
            drag2 = (tiers2[b]['watt'] / b) if b in tiers2 else None
            
            t_col1, t_col2 = "black", "black"
            font_wt1, font_wt2 = "normal", "normal"
            
            if drag1 and drag2:
                if drag1 < drag2:
                    t_col1 = c1
                    font_wt1 = "bold"
                elif drag2 < drag1:
                    t_col2 = c2
                    font_wt2 = "bold"
            
            txt1 = f"{drag1:.2f} W/mph" if drag1 else "N/A"
            txt2 = f"{drag2:.2f} W/mph" if drag2 else "N/A"
            
            tk.Label(self.table_frame, text=txt1, font=("Consolas", 10, font_wt1), fg=t_col1, bg="#f8f9fa").grid(row=row_idx, column=1, sticky="e", padx=15, pady=1)
            tk.Label(self.table_frame, text=txt2, font=("Consolas", 10, font_wt2), fg=t_col2, bg="#f8f9fa").grid(row=row_idx, column=2, sticky="e", padx=15, pady=1)
            row_idx += 1
            
        for widget in self.plot_frame.winfo_children():
            widget.destroy()
            
        t1, s1, w1, a1, th1 = extract_plot_data(self.file1)
        t2, s2, w2, a2, th2 = extract_plot_data(self.file2)
        
        fig = plt.figure(figsize=(10, 9))
        gs = fig.add_gridspec(4, 2, width_ratios=[1.5, 1])
        fig.suptitle(f'Flight Profile & Aerodynamic Efficiency (High-Res)', fontsize=14, fontweight='bold')
        
        ax1 = fig.add_subplot(gs[0, 0])
        ax2 = fig.add_subplot(gs[1, 0], sharex=ax1)
        ax3 = fig.add_subplot(gs[2, 0], sharex=ax1)
        ax4 = fig.add_subplot(gs[3, 0], sharex=ax1)
        
        ax1.plot(t1, a1, label=n1, color=c1, linewidth=1.5)
        ax1.plot(t2, a2, label=n2, color=c2, linewidth=1.5)
        ax1.set_ylabel('Altitude (ft)')
        ax1.grid(True, linestyle='--', alpha=0.5)
        ax1.legend(loc='upper right')
        
        ax2.plot(t1, s1, label=n1, color=c1, linewidth=1.5)
        ax2.plot(t2, s2, label=n2, color=c2, linewidth=1.5)
        ax2.set_ylabel('Speed (mph)')
        ax2.grid(True, linestyle='--', alpha=0.5)
        
        ax3.plot(t1, w1, label=n1, color=c1, linewidth=1.5)
        ax3.plot(t2, w2, label=n2, color=c2, linewidth=1.5)
        ax3.set_ylabel('Wattage (W)')
        ax3.grid(True, linestyle='--', alpha=0.5)

        ax4.plot(t1, th1, label=n1, color=c1, linewidth=1.5)
        ax4.plot(t2, th2, label=n2, color=c2, linewidth=1.5)
        ax4.set_ylabel('Throttle (%)')
        ax4.set_xlabel('Flight Time (Seconds)')
        ax4.grid(True, linestyle='--', alpha=0.5)
        
        ax5 = fig.add_subplot(gs[:, 1])
        ax5.set_title('Aerodynamic Drag Profile', fontweight='bold')
        
        spds1 = sorted([b for b in tiers1.keys() if b > 0])
        drg1 = [tiers1[b]['watt'] / b for b in spds1]
        spds2 = sorted([b for b in tiers2.keys() if b > 0])
        drg2 = [tiers2[b]['watt'] / b for b in spds2]

        ax5.plot(spds1, drg1, marker='o', color=c1, label=n1, linewidth=2)
        ax5.plot(spds2, drg2, marker='o', color=c2, label=n2, linewidth=2)
        ax5.set_xlabel('Speed (mph)', fontweight='bold')
        ax5.set_ylabel('Drag Cost (Watts per mph)', fontweight='bold')
        ax5.grid(True, linestyle='--', alpha=0.5)
        ax5.legend(loc='upper left')

        fig.tight_layout()
        
        canvas = FigureCanvasTkAgg(fig, master=self.plot_frame)
        canvas.draw()
        toolbar_plt = NavigationToolbar2Tk(canvas, self.plot_frame)
        toolbar_plt.update()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

if __name__ == "__main__":
    app = FlightDashboard()
    app.mainloop()