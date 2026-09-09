import json
from datetime import datetime
from kafka import KafkaProducer
from src.services.binance_api import get_precos

producer = KafkaProducer(
    bootstrap_servers='127.0.0.1:29092',
    value_serializer=lambda v: json.dumps(v).encode("utf-8")
)

TOPICO = 'cotacoes-binance'
mensagens = get_precos()

for mensagem in mensagens:
    evento = {
        'cripto':mensagem['symbol'],
        'price':mensagem['price'],
        'extract_date':datetime.now().isoformat()
    }

    producer.send(topic=TOPICO, value=evento)

producer.flush()

