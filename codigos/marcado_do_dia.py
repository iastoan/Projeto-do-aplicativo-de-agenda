import calendar
#a função do import traz o calendario no codigo sem ter quer colocar dia por dia.
ano = 2025
mes = 11
dia = 8
#variaves de ano,mes,dia contado o momento da criação

dia_semana = calendar.weekday(ano,mes,dia)

if dia_semana==0:
    print("segunda-freira")
elif dia_semana ==1:
    print("terça-freira")
elif dia_semana ==2:
    print("quarta-freira")
elif dia_semana ==3:
    print("quinta-freira")
elif dia_semana ==4:
    print("sexta-freira")
elif dia_semana ==5:
    print("sabado")
else:
    print("domingo")
