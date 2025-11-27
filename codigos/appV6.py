import flet as ft
import sqlite3
import threading
import time
import smtplib
from email.message import EmailMessage
from datetime import datetime, date as dt_date, timedelta as dt_timedelta

DB_FILENAME = "agenda.db"

# ------------- CONFIGURAÇÃO DE E-MAIL -------------
EMAIL_CONFIG = {
    "SMTP_HOST": "smtp.gmail.com",
    "SMTP_PORT": 587,
    "SMTP_USER": "appagendamentoal@gmail.com",     # seu e-mail
    "SMTP_PASS": "zkbq ndye rzhl odnm",          # senha de app (sem espaços)
    "FROM_NAME": "Agenda Pro",                     # nome que aparece no remetente
}

# Quantos minutos antes do horário do compromisso o e-mail deve ser enviado
NOTIFY_BEFORE_MINUTES = 0  # 0 = exatamente na hora
# --------------------------------------------------


# ==============================================
# FUNÇÃO PARA ENVIAR E-MAIL
# ==============================================
def send_email(to_email: str, subject: str, body: str) -> bool:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{EMAIL_CONFIG['FROM_NAME']} <{EMAIL_CONFIG['SMTP_USER']}>"
    msg["To"] = to_email
    msg.set_content(body)

    try:
        with smtplib.SMTP(EMAIL_CONFIG["SMTP_HOST"], EMAIL_CONFIG["SMTP_PORT"]) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(EMAIL_CONFIG["SMTP_USER"], EMAIL_CONFIG["SMTP_PASS"])
            smtp.send_message(msg)
        print(f"[email enviado] para {to_email} - {subject}")
        return True
    except Exception as e:
        print("[erro enviando email]", e)
        return False


# ==============================================
# BANCO DE DADOS
# ==============================================
def init_db():
    conn = sqlite3.connect(DB_FILENAME)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            email TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS compromissos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER,
            titulo TEXT NOT NULL,
            data TEXT NOT NULL,  -- formato dd/mm/aaaa
            hora TEXT NOT NULL   -- formato HH:MM
        )
    """)

    # Verifica colunas extras
    cur.execute("PRAGMA table_info(compromissos)")
    colunas = [c[1] for c in cur.fetchall()]

    if "descricao" not in colunas:
        cur.execute("ALTER TABLE compromissos ADD COLUMN descricao TEXT")

    if "notified" not in colunas:
        cur.execute("ALTER TABLE compromissos ADD COLUMN notified INTEGER DEFAULT 0")

    conn.commit()
    conn.close()


# ==============================================
# MONITOR DE COMPROMISSOS (THREAD)
# ==============================================
def monitor_loop(stop_event: threading.Event):
    """
    Fica rodando em segundo plano.
    Procura compromissos não notificados e envia e-mail quando chegar a hora.
    """
    while not stop_event.is_set():
        try:
            conn = sqlite3.connect(DB_FILENAME)
            cur = conn.cursor()

            cur.execute("""
                SELECT c.id, c.titulo, c.descricao, c.data, c.hora,
                       IFNULL(c.notified, 0),
                       u.email, u.nome
                FROM compromissos c
                JOIN usuarios u ON u.id = c.usuario_id
                WHERE IFNULL(c.notified, 0) = 0
            """)
            rows = cur.fetchall()

            now = datetime.now()

            for (
                comp_id,
                titulo,
                descricao,
                data_str,
                hora_str,
                notified,
                email,
                nome,
            ) in rows:
                # data_str formato: "dd/mm/aaaa"
                # hora_str formato: "HH:MM"
                try:
                    when_dt = datetime.strptime(
                        f"{data_str} {hora_str}", "%d/%m/%Y %H:%M"
                    )
                except Exception:
                    print(f"[erro] não consegui converter data/hora: {data_str} {hora_str}")
                    continue

                trigger_dt = when_dt - dt_timedelta(minutes=NOTIFY_BEFORE_MINUTES)

                if now >= trigger_dt:
                    subject = f"Lembrete: {titulo} — {when_dt.strftime('%d/%m/%Y %H:%M')}"
                    body_lines = [
                        f"Olá, {nome}!",
                        "",
                        "Este é um lembrete do seu compromisso:",
                        "",
                        f"Título: {titulo}",
                        f"Descrição: {descricao or '(sem descrição)'}",
                        f"Data e hora: {when_dt.strftime('%d/%m/%Y %H:%M')}",
                    ]
                    if NOTIFY_BEFORE_MINUTES > 0:
                        body_lines.append(
                            f"(Enviado {NOTIFY_BEFORE_MINUTES} minuto(s) antes do horário agendado.)"
                        )
                    body_lines.append("")
                    body_lines.append("Atenciosamente,")
                    body_lines.append(EMAIL_CONFIG["FROM_NAME"])

                    body = "\n".join(body_lines)

                    ok = send_email(email, subject, body)
                    if ok:
                        cur.execute(
                            "UPDATE compromissos SET notified = 1 WHERE id = ?",
                            (comp_id,),
                        )
                        conn.commit()

        except Exception as e:
            print("[erro no monitor_loop]", e)
        finally:
            try:
                conn.close()
            except:
                pass

        # dorme um pouco antes de checar de novo
        for _ in range(30):
            if stop_event.is_set():
                break
            time.sleep(1)


# ==============================================
# TELA PRINCIPAL
# ==============================================
def tela_principal(page, usuario):

    page.clean()
    page.title = "Agenda Pro"
    page.bgcolor = "#121212"   # mais escuro e bonito

    conn = sqlite3.connect(DB_FILENAME)
    cur = conn.cursor()

    # Buscar eventos
    def carregar_eventos():
        cur.execute(
            "SELECT titulo, descricao, data, hora FROM compromissos WHERE usuario_id = ?",
            (usuario["id"],)
        )
        return cur.fetchall()

    eventos_coluna = ft.Column(spacing=12, scroll="auto")

    # Lista de eventos
    def atualizar_lista():
        eventos_coluna.controls.clear()
        linhas = carregar_eventos()

        cores = ["#1E1E1E", "#242424", "#2A2A2A", "#1F1F1F"]

        for i, (titulo, descricao, data_ev, hora_ev) in enumerate(linhas):
            eventos_coluna.controls.append(
                ft.Container(
                    bgcolor=cores[i % len(cores)],
                    border_radius=12,
                    padding=12,
                    content=ft.Column(
                        [
                            ft.Text(titulo, weight="bold", size=19, color="white"),
                            ft.Text(f"{data_ev} • {hora_ev}", size=15, color="#DDDDDD"),
                            ft.Text(descricao or "", size=14, color="#BBBBBB")
                        ]
                    )
                )
            )
        page.update()

    atualizar_lista()

    # FORMULARIO
    titulo_tf = ft.TextField(label="Título", width=350, border_radius=10, color="white")
    desc_tf = ft.TextField(label="Descrição", width=350, border_radius=10, multiline=True, color="white")

    selected_date = ft.Text("Data: —", color="white")
    selected_time = ft.Text("Hora: —", color="white")

    date_picker = ft.DatePicker()
    time_picker = ft.TimePicker()

    page.overlay.append(date_picker)
    page.overlay.append(time_picker)

    def abrir_data(e):
        date_picker.open = True
        page.update()

    def abrir_hora(e):
        time_picker.open = True
        page.update()

    def mudou_data(e):
        if date_picker.value:
            selected_date.value = "Data: " + date_picker.value.strftime("%d/%m/%Y")
            page.update()

    def mudou_hora(e):
        if time_picker.value:
            selected_time.value = "Hora: " + time_picker.value.strftime("%H:%M")
            page.update()

    date_picker.on_change = mudou_data
    time_picker.on_change = mudou_hora

    def adicionar_evento(e):
        if not titulo_tf.value.strip():
            page.snack_bar = ft.SnackBar(ft.Text("Digite o título!"))
            page.snack_bar.open = True
            page.update()
            return

        if not date_picker.value or not time_picker.value:
            page.snack_bar = ft.SnackBar(ft.Text("Selecione data e hora!"))
            page.snack_bar.open = True
            page.update()
            return

        data_str = date_picker.value.strftime("%d/%m/%Y")
        hora_str = time_picker.value.strftime("%H:%M")

        conn = sqlite3.connect(DB_FILENAME)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO compromissos (usuario_id, titulo, descricao, data, hora)
            VALUES (?, ?, ?, ?, ?)
        """, (usuario["id"], titulo_tf.value, desc_tf.value, data_str, hora_str))
        conn.commit()
        conn.close()

        titulo_tf.value = ""
        desc_tf.value = ""
        selected_date.value = "Data: —"
        selected_time.value = "Hora: —"

        atualizar_lista()

    # MINI CALENDARIO
    hoje = dt_date.today()
    dias_coluna = ft.Column()

    def gerar_calendario():
        dias_coluna.controls.clear()
        for i in range(15):
            dia = hoje + dt_timedelta(days=i)
            dias_coluna.controls.append(
                ft.Text(
                    dia.strftime("%d/%m (%a)").upper(),
                    size=14,
                    color="white"
                )
            )
        page.update()

    gerar_calendario()

    # LAYOUT
    page.add(
        ft.Text("Agenda Pro", size=34, weight="bold", color="white"),
        ft.Text(f"Bem-vindo, {usuario['nome']}!", size=20, color="#DDDDDD"),
        ft.Divider(color="#333333"),

        ft.Row(
            [
                ft.Container(
                    width=380,
                    padding=16,
                    bgcolor="#1E1E1E",
                    border_radius=12,
                    content=ft.Column(
                        [
                            ft.Text("Novo evento", size=20, weight="bold", color="white"),
                            titulo_tf,
                            desc_tf,
                            ft.Row([ft.ElevatedButton("Escolher data", on_click=abrir_data), selected_date]),
                            ft.Row([ft.ElevatedButton("Escolher hora", on_click=abrir_hora), selected_time]),
                            ft.ElevatedButton("Adicionar evento", on_click=adicionar_evento, bgcolor="#FFAE42", color="black")
                        ],
                        spacing=12
                    )
                ),

                ft.Container(width=18),

                ft.Container(
                    expand=True,
                    padding=12,
                    bgcolor="#1E1E1E",
                    border_radius=12,
                    content=ft.Column(
                        [
                            ft.Text("Eventos", size=18, weight="bold", color="white"),
                            ft.Divider(color="#444444"),
                            eventos_coluna
                        ]
                    )
                ),

                ft.Container(
                    width=200,
                    padding=12,
                    bgcolor="#1E1E1E",
                    border_radius=12,
                    content=ft.Column(
                        [
                            ft.Text("Calendário", size=18, weight="bold", color="white"),
                            ft.Divider(color="#444444"),
                            dias_coluna
                        ]
                    )
                )
            ],
            expand=True
        )
    )


# ==============================================
# LOGIN CENTRALIZADO
# ==============================================
def main(page: ft.Page):
    init_db()
    page.bgcolor = "#121212"

    nome = ft.TextField(label="Nome", width=300, border_radius=10, color="white")
    email = ft.TextField(label="E-mail", width=300, border_radius=10, color="white")

    def entrar(e):
        if nome.value.strip() == "" or email.value.strip() == "":
            page.snack_bar = ft.SnackBar(ft.Text("Preencha nome e e-mail!"))
            page.snack_bar.open = True
            page.update()
            return

        conn = sqlite3.connect(DB_FILENAME)
        cur = conn.cursor()
        cur.execute("INSERT INTO usuarios (nome, email) VALUES (?, ?)", (nome.value, email.value))
        conn.commit()
        user_id = cur.lastrowid
        conn.close()

        tela_principal(page, {"id": user_id, "nome": nome.value, "email": email.value})

    page.add(
        ft.Column(
            [
                ft.Text("Agenda Pro", size=36, weight="bold", color="white"),
                nome,
                email,
                ft.ElevatedButton("Entrar", on_click=entrar, bgcolor="#FFAE42", color="black")
            ],
            alignment="center",
            horizontal_alignment="center"
        )
    )


# ==============================================
# THREAD DO MONITOR + APP
# ==============================================
stop_event = threading.Event()
monitor_thread = threading.Thread(
    target=monitor_loop, args=(stop_event,), daemon=True
)
monitor_thread.start()

if __name__ == "__main__":
    ft.app(target=main)

    stop_event.set()
    monitor_thread.join(timeout=2)