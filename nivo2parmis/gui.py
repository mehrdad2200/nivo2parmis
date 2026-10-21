"""پنجره‌ی گرافیکی ساده: دو فایل را انتخاب کن، یک دکمه."""
import os, queue, sys, threading, subprocess


def _open_folder(path):
    try:
        if sys.platform.startswith("win"): os.startfile(path)          # noqa
        elif sys.platform == "darwin": subprocess.Popen(["open", path])
        else: subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


def main(start_dir=None):
    import tkinter as tk
    from tkinter import filedialog, messagebox
    from .simple import find_files, run_job, summary_text

    start_dir = start_dir or os.getcwd()
    root = tk.Tk()
    root.title("انتقال تاریخچه‌ی نیوو به پارمیس")
    root.geometry("640x470")
    root.minsize(560, 420)
    pad = {"padx": 14, "pady": 6}
    nivo_var, parmis_var = tk.StringVar(), tk.StringVar()
    n0, p0 = find_files(start_dir)
    if n0: nivo_var.set(n0)
    if p0: parmis_var.set(p0)

    tk.Label(root, text="۱) فایل پشتیبان نیوو (.nivo)", anchor="e", font=("Tahoma", 10, "bold")).pack(fill="x", **pad)
    f1 = tk.Frame(root); f1.pack(fill="x", padx=14)
    tk.Entry(f1, textvariable=nivo_var, justify="left").pack(side="left", fill="x", expand=True)
    tk.Button(f1, text="انتخاب…", width=9,
              command=lambda: nivo_var.set(filedialog.askopenfilename(title="فایل نیوو", filetypes=[("Nivo backup", "*.nivo"), ("All", "*.*")]) or nivo_var.get())
              ).pack(side="left", padx=(6, 0))

    tk.Label(root, text="۲) آخرین فایل پشتیبان پارمیس (.par)", anchor="e", font=("Tahoma", 10, "bold")).pack(fill="x", **pad)
    f2 = tk.Frame(root); f2.pack(fill="x", padx=14)
    tk.Entry(f2, textvariable=parmis_var, justify="left").pack(side="left", fill="x", expand=True)
    tk.Button(f2, text="انتخاب…", width=9,
              command=lambda: parmis_var.set(filedialog.askopenfilename(title="فایل پارمیس", filetypes=[("Parmis backup", "*.par"), ("All", "*.*")]) or parmis_var.get())
              ).pack(side="left", padx=(6, 0))

    btn = tk.Button(root, text="۳) ادغام کن", font=("Tahoma", 12, "bold"), height=2, bg="#2e7d32", fg="white")
    btn.pack(fill="x", padx=14, pady=12)
    log = tk.Text(root, height=10, state="disabled", wrap="word", font=("Tahoma", 10))
    log.pack(fill="both", expand=True, padx=14, pady=(0, 12))
    q = queue.Queue()

    def write(msg):
        log.configure(state="normal"); log.insert("end", str(msg) + "\n"); log.see("end"); log.configure(state="disabled")

    def worker(n, p):
        try:
            out, rep = run_job(n, p, log=lambda *a: q.put(("log", " ".join(map(str, a)))))
            q.put(("ok", (out, rep)))
        except Exception as e:                       # noqa
            q.put(("err", str(e)))

    def poll():
        try:
            while True:
                kind, val = q.get_nowait()
                if kind == "log": write(val)
                elif kind == "err":
                    btn.configure(state="normal"); write("❌ " + val)
                    messagebox.showerror("خطا", val)
                elif kind == "ok":
                    out, rep = val
                    btn.configure(state="normal")
                    text = summary_text(rep, out); write(text)
                    messagebox.showinfo("انجام شد", text)
                    _open_folder(os.path.dirname(out))
        except queue.Empty:
            pass
        root.after(150, poll)

    def go():
        n, p = nivo_var.get().strip(), parmis_var.get().strip()
        if not (n and os.path.isfile(n)): return messagebox.showwarning("فایل نیوو", "فایل نیوو را انتخاب کنید.")
        if not (p and os.path.isfile(p)): return messagebox.showwarning("فایل پارمیس", "فایل پارمیس را انتخاب کنید.")
        btn.configure(state="disabled"); write("⏳ در حال ادغام…")
        threading.Thread(target=worker, args=(n, p), daemon=True).start()

    btn.configure(command=go)
    write("فایل‌ها را انتخاب کنید و «ادغام کن» را بزنید.\nفایل اصلی پارمیس شما تغییر نمی‌کند؛ یک فایل جدید ساخته می‌شود.")
    if n0 and p0: write(f"فایل‌های این پوشه خودکار پیدا شدند:\n  {os.path.basename(n0)}\n  {os.path.basename(p0)}")
    root.after(150, poll)
    root.mainloop()
