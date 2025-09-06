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

        self.root = tk.Tk()
        self.root.title("Jogo de Go")

        self.canvas = tk.Canvas(self.root, bg="#F0D9B5")
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Button-1>", self.on_click)
        self.canvas.bind("<Configure>", lambda event: self.draw_board())

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

        for y in range(BOARD_SIZE):
            for x in range(BOARD_SIZE):
                x1 = x_offset + x * cell_size
                y1 = y_offset + y * cell_size
                x2 = x1 + cell_size
                y2 = y1 + cell_size
                self.canvas.create_rectangle(x1, y1, x2, y2, fill="#F0D9B5", outline="black")

                if self.board[y][x] != "":
                    color = "black" if self.board[y][x] == "B" else "white"
                    self.canvas.create_oval(x1+5, y1+5, x2-5, y2-5, fill=color)

    def on_click(self, event):
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
            self.stub.PlayMove(go_pb2.MoveRequest(
                move=go_pb2.Move(x=x, y=y, color=self.color)
            ))

    def listen_events(self):
        for event in self.stub.Subscribe(go_pb2.Empty()):
            for cell in event.board.cells:
                self.board[cell.y][cell.x] = cell.color
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
