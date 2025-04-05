from socket import *
import sys
import time
from dotenv import load_dotenv
import os

# Load variables from .env into the environment
load_dotenv()

# Access the variables
CLP_IP = os.getenv('CLP_IP')

class Conexao:
    def __init__(self):

        global CLP_IP
        
        self.serverHost = CLP_IP  # IP do CLP
        self.serverPort = 2000
        self.sockobj = socket(AF_INET, SOCK_STREAM)

    def connect(self):
        print("Tentando conectar...")
        try:
            self.sockobj.connect((self.serverHost, self.serverPort))
            print('Conexão realizada!')
        except Exception as e:
            print(f"Erro na conexão: {e}")
            sys.exit()
        print(self.sockobj.getpeername())

    def publicar(self, garra, lista):
        flag = garra.to_bytes(1, byteorder="big")
        POS_DO_COMPONENTE = [i.to_bytes(4, byteorder="big", signed=True) for i in lista]
        data = flag + b''.join(POS_DO_COMPONENTE)
        self.sockobj.send(data)

    def LER_POS(self):
        dadosbraco = self.sockobj.recv(16)
        A = int.from_bytes(dadosbraco[1:4], byteorder="big", signed=True)
        B = int.from_bytes(dadosbraco[4:7], byteorder="big", signed=True)
        C = int.from_bytes(dadosbraco[7:10], byteorder="big", signed=True)
        D = int.from_bytes(dadosbraco[10:12], byteorder="big", signed=True)
        E = int.from_bytes(dadosbraco[12:14], byteorder="big", signed=True)
        F = int.from_bytes(dadosbraco[14:16], byteorder="big", signed=True)
        return [A, B, C, D, E, F]

def mover_braco(clp, POS_MOV, msg):
    clp.publicar(0, POS_MOV)
    POS_ATUAL = clp.LER_POS()
    print('Iniciando movimento.')

    while POS_ATUAL[:-1] != POS_MOV[:-1] or abs(POS_ATUAL[-1]) != abs(POS_MOV[-1]):
        POS_ATUAL = clp.LER_POS()
        print(msg)
        print(f'Posição desejada: {POS_MOV} || Posição atual: {POS_ATUAL}')
    time.sleep(2)

async def makeDraw(posicoes):
    print('###############')
    print(posicoes)
    print(len(posicoes))
    
    clp = Conexao()
    clp.connect()

    Ponto_inicial = [170, 65, -250, -3, 88, -2]

    mover_braco(clp, Ponto_inicial, msg="Indo para o ponto inicial")

    for pos in posicoes:
        mover_braco(clp, pos, msg="Movendo para posição acima do ponto")

    mover_braco(clp, Ponto_inicial, msg="Indo para o ponto inicial")
