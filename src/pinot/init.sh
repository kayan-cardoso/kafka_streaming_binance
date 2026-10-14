#!/bin/sh
CONTROLLER=http://pinot-controller:9000

echo "Aguardando o Pinot Controller..."
until curl -sf "$CONTROLLER/health" > /dev/null; do sleep 3; done

# Idempotente: se a tabela já existe, não faz nada
if curl -s "$CONTROLLER/tables" | grep -q '"cotacoes_binance"'; then
  echo "Tabela já existe, nada a fazer."
  exit 0
fi

echo "Criando schema..."
curl -s -X POST -H "Content-Type: application/json" \
  -d @/config/schema.json "$CONTROLLER/schemas"

echo "Criando tabela (com retentativas, o server pode demorar a registrar)..."
for i in $(seq 1 20); do
  code=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
    -H "Content-Type: application/json" \
    -d @/config/table.json "$CONTROLLER/tables")
  if [ "$code" = "200" ]; then echo "Tabela criada."; exit 0; fi
  echo "Tentativa $i falhou (HTTP $code), tentando de novo em 5s..."
  sleep 5
done
exit 1