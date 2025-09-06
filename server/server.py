import grpc
from concurrent import futures
import threading
import queue
import time
import sys, os

# adiciona a pasta generated/ no PYTHONPATH
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'generated'))
import go_pb2, go_pb2_grpc

SIZE = 9

# ---------- Classe do jogo ----------
class Game:
    def __init__(self):
        self.size = SIZE
        self.board = [["" for _ in range(SIZE)] for _ in range(SIZE)]
        self.turn = "B"  # Preto começa
        self.lock = threading.Lock()
        self.subscribers = []
        self.players = {}  # guarda {player_name: color}

    def join(self, player_name):
        with self.lock:
            if player_name in self.players:
                return self.players[player_name]

            if "B" not in self.players.values():
                color = "B"
            elif "W" not in self.players.values():
                color = "W"
            else:
                # Se já tiver dois jogadores
                # Por enquanto, só retorna None
                return None

            self.players[player_name] = color
            return color


    def play_move(self, x, y, color):
        with self.lock:
            if self.board[y][x] != "" or color != self.turn:
                return False

            self.board[y][x] = color
            self.turn = "W" if self.turn == "B" else "B"
            self.notify_all(color, x, y)
            return True

    def notify_all(self, color, x, y):
        event = go_pb2.GameEvent(
            type="MOVE",
            board=self.get_board_state(),
            turn=self.turn,
            msg=f"{color} jogou em ({x},{y})"
        )
        for q in self.subscribers:
            q.put(event)

    def get_board_state(self):
        cells = []
        for y in range(SIZE):
            for x in range(SIZE):
                if self.board[y][x] != "":
                    cells.append(go_pb2.Cell(x=x, y=y, color=self.board[y][x]))
        return go_pb2.BoardState(size=SIZE, cells=cells)

# ---------- Serviço gRPC ----------
class GoGameServicer(go_pb2_grpc.GoGameServicer):
    def __init__(self):
        self.game = Game()

    def JoinGame(self, request, context):
        player_color = self.game.join(request.player_name)
        return go_pb2.JoinReply(
            game_id="game1",
            me=go_pb2.PlayerInfo(player_id=request.player_name, color=player_color)
        )

    def PlayMove(self, request, context):
        self.game.play_move(request.move.x, request.move.y, request.move.color)
        return go_pb2.Empty()

    def Subscribe(self, request, context):
        q = queue.Queue()
        self.game.subscribers.append(q)
        try:
            while True:
                event = q.get()
                yield event
        except grpc.RpcError:
            self.game.subscribers.remove(q)

# ---------- Inicialização do servidor ----------
def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    go_pb2_grpc.add_GoGameServicer_to_server(GoGameServicer(), server)
    server.add_insecure_port('[::]:50051')
    server.start()
    print("Servidor gRPC rodando na porta 50051...")
    try:
        while True:
            time.sleep(86400)
    except KeyboardInterrupt:
        server.stop(0)

if __name__ == "__main__":
    serve()
