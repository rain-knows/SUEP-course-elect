import tkinter as tk
from tkinter import messagebox
import main

class GUI:
    def __init__(self, root):
        self.root = root
        self.root.title("SUEP Course Elect")

        self.username_label = tk.Label(root, text="Username")
        self.username_label.pack()
        self.username_entry = tk.Entry(root)
        self.username_entry.pack()

        self.password_label = tk.Label(root, text="Password")
        self.password_label.pack()
        self.password_entry = tk.Entry(root, show="*")
        self.password_entry.pack()

        self.login_button = tk.Button(root, text="Login", command=self.login)
        self.login_button.pack()

        self.select_courses_button = tk.Button(root, text="Select Courses", command=self.select_courses)
        self.select_courses_button.pack()

        self.view_courses_list_button = tk.Button(root, text="View Courses List", command=self.view_courses_list)
        self.view_courses_list_button.pack()

        self.export_courses_list_button = tk.Button(root, text="Export Courses List", command=self.export_courses_list)
        self.export_courses_list_button.pack()

    def login(self):
        username = self.username_entry.get()
        password = self.password_entry.get()
        try:
            main.ids.login(username, password, main.service)
            if main.ids.ok:
                messagebox.showinfo("Login", "Login successful")
            else:
                messagebox.showerror("Login", "Login failed")
        except Exception as e:
            messagebox.showerror("Login", f"Login failed: {e}")

    def select_courses(self):
        try:
            elections = main.get_elections()
            if not elections:
                messagebox.showinfo("Select Courses", "No available elections")
                return

            election_id = list(elections.values())[0] if len(elections) == 1 else self.select_election(elections)
            if not election_id:
                return

            main.head_election(election_id)
            main.thread_elect_courses_exps([], election_id)
            messagebox.showinfo("Select Courses", "Courses selected successfully")
        except Exception as e:
            messagebox.showerror("Select Courses", f"Failed to select courses: {e}")

    def select_election(self, elections):
        election_window = tk.Toplevel(self.root)
        election_window.title("Select Election")

        election_var = tk.StringVar(election_window)
        election_var.set(list(elections.keys())[0])

        election_menu = tk.OptionMenu(election_window, election_var, *elections.keys())
        election_menu.pack()

        def on_select():
            election_window.destroy()

        select_button = tk.Button(election_window, text="Select", command=on_select)
        select_button.pack()

        self.root.wait_window(election_window)
        return elections.get(election_var.get())

    def view_courses_list(self):
        try:
            elections = main.get_elections()
            if not elections:
                messagebox.showinfo("View Courses List", "No available elections")
                return

            election_id = list(elections.values())[0] if len(elections) == 1 else self.select_election(elections)
            if not election_id:
                return

            main.head_election(election_id)
            data = main.get_courses(election_id)
            courses_list = "\n".join([f"{course['id']}: {course['name']}" for course in data])
            messagebox.showinfo("Courses List", courses_list)
        except Exception as e:
            messagebox.showerror("View Courses List", f"Failed to view courses list: {e}")

    def export_courses_list(self):
        try:
            elections = main.get_elections()
            if not elections:
                messagebox.showinfo("Export Courses List", "No available elections")
                return

            election_id = list(elections.values())[0] if len(elections) == 1 else self.select_election(elections)
            if not election_id:
                return

            main.head_election(election_id)
            data = main.get_courses(election_id)
            main.export_courses_list(data, election_id)
            messagebox.showinfo("Export Courses List", "Courses list exported successfully")
        except Exception as e:
            messagebox.showerror("Export Courses List", f"Failed to export courses list: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    gui = GUI(root)
    root.mainloop()
