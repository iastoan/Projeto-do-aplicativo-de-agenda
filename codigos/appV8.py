# appV8.py
import re
import flet as ft
import sqlite3
import threading
import time
import smtplib
from email.message import EmailMessage
from datetime import datetime, date as dt_date, timedelta as dt_timedelta
from calendar import monthrange
import sys
import os

DB_FILENAME = "agenda.db"

# ------------- CONFIGURAÇÃO DE E-MAIL -------------
EMAIL_CONFIG = {
    "SMTP_HOST": "smtp.gmail.com",
    "SMTP_PORT": 587,
    "SMTP_USER": "appagendamentoal@gmail.com",
    "SMTP_PASS": "ijqg hpvh yzmn ejzf",
    "FROM_NAME": "Calendar Arrange",
}
NOTIFY_BEFORE_MINUTES = 0
# --------------------------------------------------

# regex simples para validar e-mails (não cobre todos os casos RFC mas evita entradas claramente inválidas)
EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")



def resource_path(relative_path: str) -> str:
    if getattr(sys, "frozen", False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


DB_FILENAME = resource_path("agenda.db")


def send_email(to_email: str, subject: str, body: str) -> bool:
    # validação básica do destinatário
    if not to_email or not isinstance(to_email, str) or not EMAIL_REGEX.match(to_email.strip()):
        print(f"[erro enviando email] destinatário inválido: {to_email!r} — pulando envio.")
        return False

    user = EMAIL_CONFIG.get("SMTP_USER") or ""
    passwd = EMAIL_CONFIG.get("SMTP_PASS") or ""
    if not user or not passwd:
        print("[send_email] SMTP não configurado — pulando envio.")
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{EMAIL_CONFIG['FROM_NAME']} <{user}>"
    msg["To"] = to_email
    msg.set_content(body)

    try:
        with smtplib.SMTP(EMAIL_CONFIG["SMTP_HOST"], EMAIL_CONFIG["SMTP_PORT"], timeout=15) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(user, passwd)
            smtp.send_message(msg)
        print(f"[email enviado] para {to_email} - {subject}")
        return True
    except Exception as e:
        print("[erro enviando email]", e)
        return False


def add_interval(when_dt: datetime, repeat_type: str, repeat_every: int) -> datetime:
    """
    Retorna when_dt + intervalo conforme repeat_type e repeat_every.
    repeat_type: 'Nenhuma','Minuto','Hora','Dia','Semana','Mês','Ano' (case-insensitive).
    """
    if not repeat_type:
        return when_dt
    rt = str(repeat_type).strip().lower()
    n = max(1, int(repeat_every or 1))

    if rt in ("minuto", "minutos", "minute", "minutes"):
        return when_dt + dt_timedelta(minutes=n)
    if rt in ("hora", "horas", "hour", "hours"):
        return when_dt + dt_timedelta(hours=n)
    if rt in ("dia", "dias", "day", "days"):
        return when_dt + dt_timedelta(days=n)
    if rt in ("semana", "semanas", "sem", "week", "weeks"):
        return when_dt + dt_timedelta(weeks=n)
    if rt in ("mês", "mes", "mêses", "meses", "month", "months"):
        year = when_dt.year
        month = when_dt.month + n
        day = when_dt.day
        year += (month - 1) // 12
        month = ((month - 1) % 12) + 1
        mdays = monthrange(year, month)[1]
        day = min(day, mdays)
        return when_dt.replace(year=year, month=month, day=day)
    if rt in ("ano", "anos", "year", "years"):
        year = when_dt.year + n
        try:
            return when_dt.replace(year=year)
        except ValueError:
            # 29/02 case
            return when_dt.replace(year=year, day=28)
    return when_dt


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
            data TEXT NOT NULL,
            hora TEXT NOT NULL
        )
    """)

    cur.execute("PRAGMA table_info(compromissos)")
    colunas = [c[1] for c in cur.fetchall()]

    if "descricao" not in colunas:
        try:
            cur.execute("ALTER TABLE compromissos ADD COLUMN descricao TEXT")
        except Exception:
            pass

    if "notified" not in colunas:
        try:
            cur.execute("ALTER TABLE compromissos ADD COLUMN notified INTEGER DEFAULT 0")
        except Exception:
            pass

    # colunas para repetição
    if "repeat_type" not in colunas:
        try:
            cur.execute("ALTER TABLE compromissos ADD COLUMN repeat_type TEXT DEFAULT 'Nenhuma'")
        except Exception:
            pass

    if "repeat_every" not in colunas:
        try:
            cur.execute("ALTER TABLE compromissos ADD COLUMN repeat_every INTEGER DEFAULT 1")
        except Exception:
            pass

    conn.commit()
    conn.close()


def monitor_loop(stop_event: threading.Event):
    """
    Thread que checa compromissos e envia e-mail se for hora.
    Trata repetições: quando notificado, se repeat_type != 'Nenhuma' recalcula próxima data/hora
    e atualiza a mesma linha para a próxima ocorrência.
    """
    while not stop_event.is_set():
        try:
            conn = sqlite3.connect(DB_FILENAME)
            cur = conn.cursor()
            cur.execute("""
                SELECT c.id, c.titulo, c.descricao, c.data, c.hora,
                       IFNULL(c.notified, 0),
                       u.email, u.nome,
                       IFNULL(c.repeat_type, 'Nenhuma'), IFNULL(c.repeat_every, 1)
                FROM compromissos c
                JOIN usuarios u ON u.id = c.usuario_id
                WHERE IFNULL(c.notified, 0) = 0
            """)
            rows = cur.fetchall()
            conn.close()

            now = datetime.now()

            for (comp_id, titulo, descricao, data_str, hora_str, notified, email, nome, repeat_type, repeat_every) in rows:
                try:
                    when_dt = datetime.strptime(f"{data_str} {hora_str}", "%d/%m/%Y %H:%M")
                except Exception:
                    print(f"[monitor] erro convertendo data/hora: {data_str} {hora_str}")
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
                        body_lines.append(f"(Enviado {NOTIFY_BEFORE_MINUTES} minuto(s) antes.)")
                    body_lines.append("")
                    body_lines.append("Atenciosamente,")
                    body_lines.append(EMAIL_CONFIG.get("FROM_NAME", "Agenda"))

                    body = "\n".join(body_lines)

                    ok = send_email(email, subject, body)
                    if ok:
                        try:
                            if repeat_type and str(repeat_type).strip().lower() != "nenhuma":
                                next_dt = None
                                try:
                                    next_dt = add_interval(when_dt, repeat_type, int(repeat_every or 1))
                                except Exception as ex:
                                    print("[monitor] erro calculando next_dt:", ex)
                                    next_dt = None

                                if next_dt:
                                    nd_data = next_dt.strftime("%d/%m/%Y")
                                    nd_hora = next_dt.strftime("%H:%M")
                                    conn2 = sqlite3.connect(DB_FILENAME)
                                    cur2 = conn2.cursor()
                                    cur2.execute("UPDATE compromissos SET data = ?, hora = ?, notified = 0 WHERE id = ?", (nd_data, nd_hora, comp_id))
                                    conn2.commit()
                                    conn2.close()
                                    print(f"[monitor] compromisso id={comp_id} atualizado para {nd_data} {nd_hora}")
                                else:
                                    conn2 = sqlite3.connect(DB_FILENAME)
                                    cur2 = conn2.cursor()
                                    cur2.execute("UPDATE compromissos SET notified = 1 WHERE id = ?", (comp_id,))
                                    conn2.commit()
                                    conn2.close()
                            else:
                                conn2 = sqlite3.connect(DB_FILENAME)
                                cur2 = conn2.cursor()
                                cur2.execute("UPDATE compromissos SET notified = 1 WHERE id = ?", (comp_id,))
                                conn2.commit()
                                conn2.close()
                        except Exception as ex_upd:
                            print("[monitor] erro atualizando repetição:", ex_upd)

        except Exception as e:
            print("[erro no monitor_loop]", e)

        for _ in range(30):
            if stop_event.is_set():
                break
            time.sleep(1)


# ---------------------------
# TELA PRINCIPAL (App)
# ---------------------------
def main(page: ft.Page, usuario):
    page.window.icon = resource_path("icon.png")
    page.title = "Calendar Arrange"
    page.bgcolor = "#121212"
    page.locale = "pt-BR"

    eventos_coluna = ft.Column(spacing=12, scroll="auto")

    # ----------------------------
    # funções do painel de logout
    # ----------------------------
    def cancelar_logout(e):
        try:
            logout_confirm.visible = False
            page.update()
        except Exception:
            pass

    def confirmar_logout(e):
        try:
            for ov in list(page.overlay):
                try:
                    ov.open = False
                except Exception:
                    pass
            page.overlay.clear()
        except Exception:
            pass

        try:
            page.controls.clear()
            page.dialog = None
            page.snack_bar = None
            page.update()
        except Exception:
            pass

        try:
            page.snack_bar = ft.SnackBar(ft.Text("Você saiu. Voltando ao menu..."))
            page.snack_bar.open = True
            page.update()
            time.sleep(0.25)
        except Exception:
            pass

        main(page)

    # painel inline (escondido por padrão) - usa Container para compatibilidade
    logout_confirm = ft.Container(
        content=ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon("exit_to_app", color="#FF6B6B"),
                            ft.Text(" Confirmar saída", size=16, weight="bold", color="white"),
                        ],
                        alignment=ft.MainAxisAlignment.START,
                    ),
                    ft.Text(
                        "Deseja realmente sair para o menu? Você poderá entrar com outro nome e e-mail.",
                        size=12,
                        color="#BBBBBB"
                    ),
                    ft.Row(
                        [
                            ft.ElevatedButton("Sair para o menu", bgcolor="#FF6B6B", on_click=confirmar_logout),
                            ft.TextButton("Cancelar", on_click=cancelar_logout),
                        ],
                        alignment=ft.MainAxisAlignment.END,
                        spacing=12
                    )
                ],
                spacing=8,
                tight=True
            ),
            padding=12,
            bgcolor="#1E1E1E",
            border_radius=8
        ),
        padding=12,
        visible=False,
        expand=False
    )

    # ----------------------------
    # restante das funções da tela
    # ----------------------------
    def carregar_eventos():
        conn = sqlite3.connect(DB_FILENAME)
        cur = conn.cursor()
        # inclui fields de repetição para exibição
        cur.execute("""
            SELECT id, titulo, descricao, data, hora,
                   IFNULL(repeat_type, 'Nenhuma'), IFNULL(repeat_every,1)
            FROM compromissos
            WHERE usuario_id = ?
            ORDER BY data, hora
        """, (usuario["id"],))
        rows = cur.fetchall()
        conn.close()
        print(f"[DB] carregar_eventos -> {len(rows)} linhas")
        return rows

    def deletar_evento(evento_id):
        print(f"[DB] deletar_evento chamado para id={evento_id}")
        conn2 = sqlite3.connect(DB_FILENAME)
        cur2 = conn2.cursor()
        cur2.execute("DELETE FROM compromissos WHERE id = ?", (evento_id,))
        conn2.commit()
        conn2.close()

    def atualizar_lista():
        eventos_coluna.controls.clear()
        linhas = carregar_eventos()
        cores = ["#1E1E1E", "#242424", "#2A2A2A", "#1F1F1F"]

        for i, (comp_id, titulo, descricao, data_ev, hora_ev, repeat_type, repeat_every) in enumerate(linhas):
            def on_click_delete(e, cid=comp_id, ct=titulo):
                print(f"[UI] delete handler chamado — id={cid} titulo='{ct}'")
                deletar_evento(cid)
                page.snack_bar = ft.SnackBar(ft.Text("Compromisso removido."))
                page.snack_bar.open = True
                atualizar_lista()
                page.update()

            # montar texto de repetição para exibir (se houver)
            repeat_text = ""
            try:
                if repeat_type and str(repeat_type).strip().lower() != "nenhuma":
                    repeat_text = f" • Repete: {repeat_every} {repeat_type}"
            except Exception:
                repeat_text = ""

            eventos_coluna.controls.append(
                ft.Container(
                    bgcolor=cores[i % len(cores)],
                    border_radius=12,
                    padding=12,
                    content=ft.Row(
                        alignment="spaceBetween",
                        controls=[
                            ft.Column(
                                [
                                    ft.Text(titulo, weight="bold", size=19, color="white"),
                                    # data/hora + repetição separados, repetição em branco também
                                    ft.Row(
                                        [
                                            ft.Text(f"{data_ev} • {hora_ev}", size=15, color="#DDDDDD"),
                                            ft.Text(repeat_text, size=15, color="white", weight="bold")
                                        ],
                                        spacing=6
                                    ),
                                    ft.Text(descricao or "", size=14, color="#BBBBBB")
                                ],
                                expand=True
                            ),
                            ft.IconButton(
                                icon="delete",
                                icon_color="red",
                                tooltip="Excluir evento",
                                on_click=on_click_delete
                            )
                        ]
                    )
                )
            )
        page.update()

    # formulário
    titulo_tf = ft.TextField(label="Título", width=350, border_radius=10, color="white")
    desc_tf = ft.TextField(label="Descrição", width=350, border_radius=10, multiline=True, color="white")

    selected_date = ft.Text("Data: —", color="white")
    selected_time = ft.Text("Hora: —", color="white")

    # controles de repetição
    # usamos ft.Text as label (com cor branca) para compatibilidade e visibilidade
    repeat_label = ft.Text("Repetição", color="white")
    repeat_dropdown = ft.Dropdown(
        width=200,
        value="Nenhuma",
        text_style=ft.TextStyle(color="white"),
        options=[
            ft.dropdown.Option("Nenhuma"),
            ft.dropdown.Option("Minuto"),
            ft.dropdown.Option("Hora"),
            ft.dropdown.Option("Dia"),
            ft.dropdown.Option("Semana"),
            ft.dropdown.Option("Mês"),
            ft.dropdown.Option("Ano"),
        ]
    )

    repeat_every_label = ft.Text("Intervalo (nº)", color="white")
    repeat_every_tf = ft.TextField(width=120, value="1", color="white")

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

        repeat_type_val = repeat_dropdown.value or "Nenhuma"
        try:
            repeat_every_val = int(repeat_every_tf.value)
        except Exception:
            repeat_every_val = 1

        conn3 = sqlite3.connect(DB_FILENAME)
        cur3 = conn3.cursor()
        cur3.execute("""
            INSERT INTO compromissos (usuario_id, titulo, descricao, data, hora, repeat_type, repeat_every)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (usuario["id"], titulo_tf.value, desc_tf.value, data_str, hora_str, repeat_type_val, repeat_every_val))
        conn3.commit()
        conn3.close()

        titulo_tf.value = ""
        desc_tf.value = ""
        selected_date.value = "Data: —"
        selected_time.value = "Hora: —"
        repeat_dropdown.value = "Nenhuma"
        repeat_every_tf.value = "1"

        atualizar_lista()
        page.update()

    # mini calendário
    hoje = dt_date.today()
    dias_coluna = ft.Column()

    def gerar_calendario():
        dias_coluna.controls.clear()
        dias_semana = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
        for i in range(15):
            dia = hoje + dt_timedelta(days=i)
            nome_dia = dias_semana[dia.weekday()]
            dias_coluna.controls.append(
                ft.Text(f"{dia.strftime('%d/%m')} ({nome_dia})", size=14, color="white")
            )
        page.update()

    gerar_calendario()

    # função que mostra o painel de logout (chamada pelo botão Sair)
    def efetuar_logout(e):
        print("[LOGOUT] botão Sair clicado — usando painel inline")
        logout_confirm.visible = True
        try:
            if logout_confirm in page.controls:
                page.controls.remove(logout_confirm)
            page.controls.insert(0, logout_confirm)
        except Exception:
            pass
        page.update()

    # layout: coloque o painel logout_confirm como primeiro controle
    page.add(
        logout_confirm,
        ft.Row(
            [
                ft.Column(
                    [
                        ft.Text("Calendar Arrange", size=34, weight="bold", color="white"),
                        ft.Text(f"Bem-vindo, {usuario['nome']}!", size=20, color="#DDDDDD"),
                    ],
                    expand=True
                ),
                ft.ElevatedButton("Sair", on_click=efetuar_logout, bgcolor="#FF6B6B")
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER
        ),
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
                            # label + dropdown (com label separado em branco)
                            repeat_label,
                            repeat_dropdown,
                            ft.Row([ft.Text("A cada", color="white"), repeat_every_tf, ft.Text("unidade(s)", color="white")], spacing=8),
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

    # primeira atualização
    atualizar_lista()


# ---------------------------
# TELA DE LOGIN / ENTRY POINT
# ---------------------------
def main(page: ft.Page):
    init_db()
    page.bgcolor = "#121212"
    page.locale = "pt-BR"

    nome = ft.TextField(label="Nome", width=300, border_radius=10, color="white")
    email = ft.TextField(label="E-mail", width=300, border_radius=10, color="white")

    def entrar(e):
        if nome.value.strip() == "" or email.value.strip() == "":
            page.snack_bar = ft.SnackBar(ft.Text("Preencha nome e e-mail!"))
            page.snack_bar.open = True
            page.update()
            return

        # valida e-mail (simples)
        if not EMAIL_REGEX.match(email.value.strip()):
            page.snack_bar = ft.SnackBar(ft.Text("E-mail inválido. Use o formato exemplo@dominio.com"))
            page.snack_bar.open = True
            page.update()
            return

        conn = sqlite3.connect(DB_FILENAME)
        cur = conn.cursor()
        cur.execute("INSERT INTO usuarios (nome, email) VALUES (?, ?)", (nome.value.strip(), email.value.strip()))
        conn.commit()
        user_id = cur.lastrowid
        conn.close()

        main(page, {"id": user_id, "nome": nome.value.strip(), "email": email.value.strip()})

    page.add(
        ft.Container(
            expand=True,
            alignment=ft.alignment.center,
            content=ft.Column(
                [
                    ft.Text("Calendar Arrange", size=36, weight="bold", color="white"),
                    nome,
                    email,
                    ft.ElevatedButton("Entrar", on_click=entrar, bgcolor="#FFAE42", color="black")
                ],
                alignment="center",
                horizontal_alignment="center",
                spacing=20
            )
        )
    )


# ============================
# MONITOR THREAD INICIADO
# ============================
stop_event = threading.Event()
monitor_thread = threading.Thread(target=monitor_loop, args=(stop_event,), daemon=True)
monitor_thread.start()

if __name__ == "__main__":
    ft.app(target=main)
    stop_event.set()
    monitor_thread.join(timeout=2)
