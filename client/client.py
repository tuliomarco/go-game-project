import tkinter as tk
import grpc
import threading
import sys, os

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'generated'))
import go_pb2, go_pb2_grpc

SERVER_ADDRESS = "localhost:50051"
BOARD_SIZE = 9  # 9x9
MARGIN = 30     # margem em pixels

class GoClientApp:
    def __init__(self, stub, player_color):
        self.stub = stub
        self.color = player_color
        self.board = [["" for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
        self.turn = "B"  # começa com pretas até vir evento

        self.root = tk.Tk()
        self.root.title("Jogo de Go")

        # --- Canvas do tabuleiro ---
        self.canvas = tk.Canvas(self.root, bg="#F0D9B5")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.canvas.bind("<Button-1>", self.on_click)
        self.canvas.bind("<Configure>", lambda event: self.draw_board())

        # --- Label para mostrar de quem é a vez ---
        self.turn_label = tk.Label(self.root, text="Vez: Pretas", font=("Arial", 12, "bold"))
        self.turn_label.pack(pady=5)

        # --- Botão "Passar a vez" ---
        self.pass_button = tk.Button(self.root, text="Passar a vez", command=self.pass_turn)
        self.pass_button.pack(pady=5)

        # Thread para ouvir eventos do servidor
        threading.Thread(target=self.listen_events, daemon=True).start()

        self.draw_board()
        self.root.mainloop()

    def draw_board(self):
        self.canvas.delete("all")
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()

        # calcula tamanho disponível subtraindo margens
        available_width = width - 2*MARGIN
        available_height = height - 2*MARGIN
        board_size_px = min(available_width, available_height)
        cell_size = board_size_px / BOARD_SIZE

        # centraliza considerando margens
        x_offset = MARGIN + (available_width - board_size_px) / 2
        y_offset = MARGIN + (available_height - board_size_px) / 2

        # desenhar linhas da grade
        for i in range(BOARD_SIZE + 1):
            # linhas horizontais
            self.canvas.create_line(
                x_offset, y_offset + i*cell_size,
                x_offset + board_size_px, y_offset + i*cell_size,
                fill="black"
            )
            # linhas verticais
            self.canvas.create_line(
                x_offset + i*cell_size, y_offset,
                x_offset + i*cell_size, y_offset + board_size_px,
                fill="black"
            )

        # desenhar pedras
        for y in range(BOARD_SIZE):
            for x in range(BOARD_SIZE):
                if self.board[y][x] != "":
                    color = "black" if self.board[y][x] == "B" else "white"
                    cx = x_offset + x * cell_size + cell_size/2
                    cy = y_offset + y * cell_size + cell_size/2
                    r = cell_size/2 - 4
                    self.canvas.create_oval(cx-r, cy-r, cx+r, cy+r, fill=color, outline="black")

    def on_click(self, event):
        if self.color != self.turn:
            print("Não é sua vez!")
            return

        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()

        available_width = width - 2*MARGIN
        available_height = height - 2*MARGIN
        board_size_px = min(available_width, available_height)
        cell_size = board_size_px / BOARD_SIZE

        x_offset = MARGIN + (available_width - board_size_px) / 2
        y_offset = MARGIN + (available_height - board_size_px) / 2

        x = int((event.x - x_offset) // cell_size)
        y = int((event.y - y_offset) // cell_size)

        if 0 <= x < BOARD_SIZE and 0 <= y < BOARD_SIZE:
            reply = self.stub.PlayMove(go_pb2.MoveRequest(
                move=go_pb2.Move(x=x, y=y, color=self.color)
            ))
            if not reply.success:
                print("Erro:", reply.msg)


    def pass_turn(self):
        if self.color != self.turn:
            print("Não é sua vez para passar!")
            return
        self.stub.PassTurn(go_pb2.PlayerInfo(player_id="tmp", color=self.color))

    def listen_events(self):
        for event in self.stub.Subscribe(go_pb2.SubscribeRequest(
            game_id="default", player_id="anon"
        )):
            # Atualizar tabuleiro
            self.board = [["" for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
            for cell in event.board.cells:
                self.board[cell.y][cell.x] = cell.color

            # Atualizar turno
            self.turn = event.turn
            if self.turn == "B":
                self.turn_label.config(text="Vez: Pretas")
            else:
                self.turn_label.config(text="Vez: Brancas")

            # Debug opcional no terminal
            print(f"Agora é a vez das {self.turn}")

            # Redesenhar tabuleiro
            self.draw_board()


def main():
    channel = grpc.insecure_channel(SERVER_ADDRESS)
    stub = go_pb2_grpc.GoGameStub(channel)

    player_name = input("Digite seu nome: ")
    join_reply = stub.JoinGame(go_pb2.JoinRequest(player_name=player_name))
    print(f"Você entrou como: {join_reply.me.color}")

    GoClientApp(stub, join_reply.me.color)

if __name__ == "__main__":
    main()