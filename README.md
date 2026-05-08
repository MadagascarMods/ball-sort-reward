# Ball Sort Reward Engine

Web interface para o ClassicBallSortPuzzle Reward API.

## Funcionalidades

- Campo para configurar GAID (Google Advertising ID)
- AD_IDs randomizados automaticamente
- Ajuste manual do LTV Range
- Suporte a até 2 sessões simultâneas
- Console em tempo real via WebSocket
- Interface dark/hacker theme

## Deploy na Render

1. Conecte este repositório na Render
2. Selecione "Web Service"
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `gunicorn --worker-class eventlet -w 1 --bind 0.0.0.0:$PORT app:app`

## Tecnologias

- Python 3.11
- Flask + Flask-SocketIO
- Gunicorn + Eventlet
- HTML/CSS/JS (vanilla)
