import flet as ft
from datetime import datetime, timedelta
import sqlite3, threading, time, smtplib
from email.message import EmailMessage

# ==================== CONFIGURAÇÃO ====================
EMAIL_CONFIG = {
    "SMTP_HOST": "smtp.gmail.com",
    "SMTP_PORT": 587,
    "SMTP_USER": "wandersonsantosoficialst@gmail.com",
    "SMTP_PASS": "rjar qrot ymvd vuee",  # senha de app do Gmail
    "FROM_NAME": "App de Notificações"
}
DB_FILENAME = "notificacoes.db"
NOTIFY_BEFORE_MINUTES = 0
# ======================================================

# ---------- BANCO DE DADOS ----------
def init_db():
    conn = sqlite3.connect(DB_FILENAME, check_same_thread=False)
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL
    )""")
    c.execute("""
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        message TEXT NOT NULL,
        when_ts INTEGER NOT NULL,
        notified INTEGER DEFAULT 0,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )""")
    conn.commit()
    return conn

db_conn = init_db()

def get_or_create_user(email):
    cur = db_conn.cursor()
    cur.execute("SELECT id FROM users WHERE email=?", (email,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute("INSERT INTO users (email) VALUES (?)", (email,))
    db_conn.commit()
    return cur.lastrowid

def add_event(user_id, message, when_ts):
    cur = db_conn.cursor()
    cur.execute("INSERT INTO events (user_id, message, when_ts) VALUES (?, ?, ?)", (user_id, message, when_ts))
    db_conn.commit()

def list_events(user_id):
    cur = db_conn.cursor()
    cur.execute("SELECT id, message, when_ts, notified FROM events WHERE user_id=? ORDER BY when_ts", (user_id,))
    return cur.fetchall()

def mark_notified(event_id):
    cur = db_conn.cursor()
    cur.execute("UPDATE events SET notified=1 WHERE id=?", (event_id,))
    db_conn.commit()

def delete_event(event_id):
    cur = db_conn.cursor()
    cur.execute("DELETE FROM events WHERE id=?", (event_id,))
    db_conn.commit()

# ---------- ENVIO DE EMAIL ----------
def send_email(to_email, subject, body):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{EMAIL_CONFIG['FROM_NAME']} <{EMAIL_CONFIG['SMTP_USER']}>"
    msg["To"] = to_email
    msg.set_content(body)
    try:
        with smtplib.SMTP(EMAIL_CONFIG["SMTP_HOST"], EMAIL_CONFIG["SMTP_PORT"]) as smtp:
            smtp.starttls()
            smtp.login(EMAIL_CONFIG["SMTP_USER"], EMAIL_CONFIG["SMTP_PASS"])
            smtp.send_message(msg)
        print(f"[E-MAIL ENVIADO] {to_email}: {subject}")
        return True
    except Exception as e:
        print("[ERRO EMAIL]", e)
        return False

# ---------- MONITOR ----------
def monitor_loop(stop_event):
    while not stop_event.is_set():
        now = datetime.now()
        cutoff = now + timedelta(minutes=NOTIFY_BEFORE_MINUTES)
        cur = db_conn.cursor()
        cur.execute("""
            SELECT e.id, e.message, e.when_ts, u.email 
            FROM events e JOIN users u ON e.user_id = u.id
            WHERE e.notified=0 AND e.when_ts <= ?""", (int(cutoff.timestamp()),))
        rows = cur.fetchall()
        for event_id, message, when_ts, email in rows:
            when_dt = datetime.fromtimestamp(when_ts)
            subject = f"Lembrete: {when_dt.strftime('%d/%m/%Y %H:%M')}"
            body = f"Olá!\n\nMensagem: {message}\nData/hora: {when_dt}\n\nAtenciosamente,\n{EMAIL_CONFIG['FROM_NAME']}"
            if send_email(email, subject, body):
                mark_notified(event_id)
        for _ in range(20):
            if stop_event.is_set():
                break
            time.sleep(1)

# ---------- INTERFACE FLET ----------
def main(page: ft.Page):
    page.title = "Notificações por E-mail"
    page.window_width = 850
    page.window_height = 600

    state = {"user_id": None, "email": None}

    email_tf = ft.TextField(label="E-mail", width=400)
    login_msg = ft.Text("", color=ft.Colors.RED)

    # ==== LOGIN ====
    def do_login(e):
        email = email_tf.value.strip()
        if not email or "@" not in email:
            login_msg.value = "Digite um e-mail válido."
            page.update()
            return
        uid = get_or_create_user(email)
        state["user_id"] = uid
        state["email"] = email
        show_main_ui()

    login_btn = ft.ElevatedButton("Entrar", on_click=do_login)
    login_view = ft.Column(
        [ft.Text("Login (apenas e-mail)", style="headlineMedium"), email_tf, login_btn, login_msg],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        alignment=ft.MainAxisAlignment.CENTER,
    )

    # ==== PRINCIPAL ====
    def show_main_ui():
        page.clean()

        message_tf = ft.TextField(label="Mensagem do evento", width=400, multiline=True)
        selected_date = ft.Text("Data não selecionada")
        selected_time = ft.Text("Hora não selecionada")
        add_msg = ft.Text("", color=ft.Colors.RED)
        events_list = ft.ListView(expand=True, spacing=8, padding=8)

        # DATE PICKER
        date_picker = ft.DatePicker()
        def open_date_picker(e):
            page.open(date_picker)
        def on_date_selected(e):
            if e.control.value:
                selected_date.value = f"Data: {e.control.value.strftime('%d/%m/%Y')}"
                page.update()
        date_picker.on_change = on_date_selected

        # TIME PICKER
        time_picker = ft.TimePicker()
        def open_time_picker(e):
            page.open(time_picker)
        def on_time_selected(e):
            if e.control.value:
                selected_time.value = f"Hora: {e.control.value.strftime('%H:%M')}"
                page.update()
        time_picker.on_change = on_time_selected

        def refresh_events():
            events_list.controls.clear()
            rows = list_events(state["user_id"])
            for event_id, message, when_ts, notified in rows:
                when_dt = datetime.fromtimestamp(when_ts)
                badge = "✅" if notified else "⏰"
                txt = f"{when_dt.strftime('%d/%m/%Y %H:%M')} — {message[:50]}"
                row = ft.Row(
                    [
                        ft.Text(badge),
                        ft.Text(txt),
                        ft.Container(expand=True),
                        ft.IconButton(ft.Icons.DELETE, on_click=lambda e, i=event_id: on_delete(i)),
                    ]
                )
                events_list.controls.append(row)
            page.update()

        def on_delete(event_id):
            delete_event(event_id)
            refresh_events()
            page.snack_bar = ft.SnackBar(ft.Text("Evento excluído."), open=True)
            page.update()

        def add_event_handler(e):
            msg = message_tf.value.strip()
            if not msg:
                add_msg.value = "Escreva a mensagem."
                page.update()
                return
            if not date_picker.value or not time_picker.value:
                add_msg.value = "Escolha data e hora."
                page.update()
                return
            when_dt = datetime.combine(date_picker.value, time_picker.value)
            if when_dt < datetime.now():
                add_msg.value = "A data/hora deve ser futura."
                page.update()
                return
            add_event(state["user_id"], msg, int(when_dt.timestamp()))
            message_tf.value = ""
            add_msg.value = "Evento salvo!"
            refresh_events()
            page.update()

        def logout(e):
            state["user_id"] = None
            state["email"] = None
            page.clean()
            page.add(login_view)
            page.update()

        # Layout principal
        page.add(
            ft.Column([
                ft.Row([
                    ft.Text(f"Usuário: {state['email']}"),
                    ft.Container(expand=True),
                    ft.ElevatedButton("Logout", on_click=logout)
                ]),
                ft.Divider(),
                ft.Row([
                    ft.Column([
                        ft.Text("Novo evento", style="titleLarge"),
                        message_tf,
                        ft.Row([ft.ElevatedButton("Selecionar data", on_click=open_date_picker), selected_date]),
                        ft.Row([ft.ElevatedButton("Selecionar hora", on_click=open_time_picker), selected_time]),
                        ft.Row([ft.ElevatedButton("Agendar evento", on_click=add_event_handler), add_msg])
                    ]),
                    ft.VerticalDivider(),
                    ft.Column([ft.Text("Eventos agendados", style="titleMedium"), events_list], expand=True)
                ], expand=True)
            ])
        )

        refresh_events()
        page.update()

    page.add(login_view)

# ========== EXECUÇÃO ==========
stop_event = threading.Event()
monitor_thread = threading.Thread(target=monitor_loop, args=(stop_event,), daemon=True)
monitor_thread.start()

if __name__ == "__main__":
    try:
        ft.app(target=main)
    finally:
        stop_event.set()
        monitor_thread.join(timeout=2)
