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
        self.players = {}
        self.captured = {"B": 0, "W": 0}  # peças capturadas

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
        
    # -------- Funções auxiliares de grupos --------
    def get_group(self, x, y):
        """Retorna todas as pedras conectadas ao ponto (x,y) da mesma cor"""
        color = self.board[y][x]
        if color == "":
            return set()
        
        visited = set()
        stack = [(x, y)]
        while stack:
            cx, cy = stack.pop()
            if (cx, cy) in visited:
                continue
            visited.add((cx, cy))
            # vizinhos ortogonais
            for nx, ny in [(cx-1, cy), (cx+1, cy), (cx, cy-1), (cx, cy+1)]:
                if 0 <= nx < self.size and 0 <= ny < self.size:
                    if self.board[ny][nx] == color and (nx, ny) not in visited:
                        stack.append((nx, ny))
        return visited

    def get_liberties(self, group):
        """Retorna o conjunto de casas vazias adjacentes a um grupo"""
        liberties = set()
        for (x, y) in group:
            for nx, ny in [(x-1, y), (x+1, y), (x, y-1), (x, y+1)]:
                if 0 <= nx < self.size and 0 <= ny < self.size:
                    if self.board[ny][nx] == "":
                        liberties.add((nx, ny))
        return liberties

    def remove_group(self, group, captor_color):
        """Remove um grupo capturado e soma no score do captor"""
        for (x, y) in group:
            self.board[y][x] = ""
        self.captured[captor_color] += len(group)

    # -------- Jogada --------
    def play_move(self, x, y, color):
        with self.lock:
            # posição ocupada ou jogada fora de turno
            if self.board[y][x] != "" or color != self.turn:
                return False

            # coloca pedra
            self.board[y][x] = color

            # checa vizinhos adversários
            opponent = "W" if color == "B" else "B"
            to_capture = []
            for nx, ny in [(x-1, y), (x+1, y), (x, y-1), (x, y+1)]:
                if 0 <= nx < self.size and 0 <= ny < self.size:
                    if self.board[ny][nx] == opponent:
                        group = self.get_group(nx, ny)
                        if len(self.get_liberties(group)) == 0:
                            to_capture.append(group)

            # captura grupos adversários
            for group in to_capture:
                self.remove_group(group, color)

            # checa suicídio (se a própria pedra ficou sem liberdades e não capturou ninguém)
            my_group = self.get_group(x, y)
            if len(self.get_liberties(my_group)) == 0 and not to_capture:
                # inválido -> desfaz jogada
                self.board[y][x] = ""
                return False

            # troca turno
            self.turn = opponent
            self.notify_all(color, x, y)
            return True

    def notify_all(self, color, x, y, passed=False):
        event = go_pb2.GameEvent(
            type="PASS" if passed else "MOVE",
            board=self.get_board_state(),
            turn=self.turn,  # <<< aqui
            msg=f"{color} passou a vez" if passed else f"{color} jogou em ({x},{y})"
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
    
    def pass_turn(self, player_color):
        with self.lock:
            if player_color == self.turn:
                self.turn = "W" if self.turn == "B" else "B"
                self.notify_all(player_color, -1, -1, passed=True)
                return True
            return False

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
        ok = self.game.play_move(request.move.x, request.move.y, request.move.color)
        if ok:
            return go_pb2.MoveReply(success=True, msg="Jogada realizada")
        else:
            return go_pb2.MoveReply(success=False, msg="Jogada inválida")
    

    def Subscribe(self, request, context):
        q = queue.Queue()
        self.game.subscribers.append(q)
        try:
            while True:
                event = q.get()
                yield event
        except grpc.RpcError:
            self.game.subscribers.remove(q)

    def PassTurn(self, request, context):
        with self.game.lock:
            if request.color == self.game.turn:
                self.game.turn = "W" if self.game.turn == "B" else "B"
                event = go_pb2.GameEvent(
                    type="PASS",
                    board=self.game.get_board_state(),
                    turn=self.game.turn,
                    msg=f"{request.color} passou a vez"
                )
                for q in self.game.subscribers:
                    q.put(event)
                return go_pb2.Empty()
            else:
                # se não for a vez dele, não faz nada
                return go_pb2.Empty()

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
