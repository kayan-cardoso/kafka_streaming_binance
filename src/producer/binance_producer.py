import json
from datetime import datetime
from kafka import KafkaProducer
from kafka.admin import KafkaAdminClient, NewTopic

from src.services.binance_api import get_precos

TOPICO = 'cotacoes-binance'
admin = KafkaAdminClient(bootstrap_servers='kafka:9092')

try:
    admin.create_topics([
        NewTopic(name=TOPICO, num_partitions=3, replication_factor=1)
    ])
except:
    pass

producer = KafkaProducer(
    bootstrap_servers='kafka:9092',
    value_serializer=lambda v: json.dumps(v).encode("utf-8")
)


mensagens = get_precos()
print(f'foram captadas {len(mensagens)} mensagens.')

for mensagem in mensagens:
    evento = {
        'cripto':mensagem['symbol'],
        'price':mensagem['price'],
        'extract_date':datetime.now().isoformat()
    }

    producer.send(topic=TOPICO, value=evento)

producer.flush()

