import anthropic
import json
import socket
import os
from pathlib import Path


class NvimConversationManager:
    def __init__(self, conv_dir: Path = Path("/home/scossar/nvim_claude")):
        self.conv_dir = conv_dir
        if not self.conv_dir.exists():
            raise ValueError(f"Conversation directory '{self.conv_dir}' doesn't exist")
        self.conv_name = None
        self.json_file = None
        self.messages = None
        self.client = anthropic.Anthropic()

    def set_conversation(self, name: str):
        self.conv_name = name
        self.json_file = self.conv_dir / f"{name}.json"

    def load_conversation(self, name: str):
        self.set_conversation(name)
        try:
            with open(self.json_file, "r") as f:
                messages = json.load(f)
        except FileNotFoundError:
            messages = []
        self.messages = messages

    def save_conversation(self, messages: list):
        with open(self.json_file, "w") as f:
            json.dump(messages, f, indent=2)

    def append_message(self, role: str, content: str):
        message = {}
        message["role"] = role
        message["content"] = content
        self.messages.append(message)

    def send_messages(self) -> str:
        response = self.client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=8192,
            temperature=0.7,
            messages=self.messages
        )

        content = response.content[0].text
        self.append_message("assistant", content)
        self.save_conversation(self.messages)
        return content


nvim_conversation_manager = NvimConversationManager()
SOCKET_PATH = "/tmp/nvim-python.sock"

if os.path.exists(SOCKET_PATH):
    os.remove(SOCKET_PATH)

server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
server.bind(SOCKET_PATH)
server.listen(1)


def read_until_delimiter(conn):
    data = ""
    request_id = None
    while True:
        chunk = conn.recv(4096).decode("utf-8")
        if not chunk:
            return None, None

        data += chunk

        if "---END---" in data:
            # Split all content before the delimiter
            message = data.split("---END---")[0]

            # Split the first line as the request ID
            parts = message.split("\n", 1)
            if len(parts) == 2:
                request_id, data = parts
            else:
                return None, None

            return request_id, data


while True:
    conn, addr = server.accept()
    try:
        while True:
            request_id, data = read_until_delimiter(conn)
            if not data:
                break

            try:
                data_dict = json.loads(data)
                filename = data_dict["filename"]
                conversation_name = Path(filename).stem
                content = data_dict["content"]

                nvim_conversation_manager.load_conversation(conversation_name)
                nvim_conversation_manager.append_message("user", content)
                response = nvim_conversation_manager.send_messages()
                print(f"Server received data from: {filename}")

                full_response = f"{request_id}\n{response}\n---END---\n"
                conn.sendall(full_response.encode("utf-8"))
            except json.JSONDecodeError as e:
                print(f"JSON decode error: {e}")
                error_response = f"{request_id}\nError: Invalid JSON\n---END---\n"
                conn.sendall(error_response.encode("utf-8"))

    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

