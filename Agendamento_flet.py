import flet as ft

def agendamento_flet(page: ft.Page):
    page.title = ("App de Agendamento")
    
    def cadastrar(e):
        print(pessoa.value)


    txt_titulo = ft.Text("cadastro de E-mail:")
    pessoa = ft.TextField(label="Digite o seu E-mail", text_align=ft.TextAlign.LEFT)
    btn_cadastro = ft.ElevatedButton("Cadastrar", on_click=cadastrar)

    page.add(txt_titulo, pessoa, btn_cadastro)

ft.app(target=agendamento_flet)