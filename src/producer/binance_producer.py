import json
import logging
from time import sleep
from datetime import datetime
from kafka import KafkaProducer
from kafka.admin import KafkaAdminClient, NewTopic

from src.services.binance_api import get_precos

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger()

TOPICO = 'cotacoes-binance'
SEGUNDOS = 30
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
logger.info('Producer conectado com sucesso, iniciando envio das mensagens.')
while True:
    try:
        mensagens = get_precos()

        for mensagem in mensagens:
            evento = {
                'cripto':mensagem['symbol'],
                'price':mensagem['price'],
                'extract_date':datetime.now().isoformat()
            }

            producer.send(topic=TOPICO, value=evento)

        producer.flush()
        logger.info(f'✅ As Mensagens foram enviadas com sucesso.')
        
    except Exception as e:
        logger.warning(f'Erro ao enviar a mensagem: {e}.')

    sleep(SEGUNDOS)

