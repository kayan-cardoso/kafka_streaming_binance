import os
import time

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from pinotdb import connect

PINOT_HOST = os.getenv("PINOT_BROKER_HOST", "localhost")
PINOT_PORT = int(os.getenv("PINOT_BROKER_PORT", "8099"))
TABELA = "cotacoes_binance"

JANELAS = {"15 minutos": 15 * 60, "1 hora": 60 * 60, "6 horas": 6 * 60 * 60, "24 horas": 24 * 60 * 60}
PADRAO = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
PADRAO_CORR = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT",
    "DOGEUSDT", "LINKUSDT", "AVAXUSDT", "LTCUSDT", "TRXUSDT", "DOTUSDT",
]
STABLES = {"USDCUSDT", "FDUSDUSDT", "USD1USDT", "RLUSDUSDT", "UUSDT", "EURUSDT"}
VERDE, VERMELHO, AZUL = "#2e9e5b", "#d64545", "#4c78a8"
MARGEM = dict(l=0, r=0, t=40, b=0)

st.set_page_config(page_title="Cotações Binance em tempo real",
                   layout="wide",
                   page_icon='💹')


@st.cache_resource
def conectar():
    return connect(host=PINOT_HOST, port=PINOT_PORT, path="/query/sql", scheme="http")


def consultar(sql: str) -> pd.DataFrame:
    cursor = conectar().cursor()
    cursor.execute(sql)
    colunas = [c[0] for c in cursor.description]
    return pd.DataFrame(cursor.fetchall(), columns=colunas)


def limite_ms(janela_s: int) -> int:
    return int((time.time() - janela_s) * 1000)


@st.cache_data(ttl=300)
def listar_criptos() -> list[str]:
    df = consultar(f"SELECT DISTINCT cripto FROM {TABELA} ORDER BY cripto LIMIT 1000")
    return df["cripto"].tolist()


def buscar_precos(criptos: list[str], janela_s: int) -> pd.DataFrame:
    lista = ", ".join("'" + c.replace("'", "''") + "'" for c in criptos)
    df = consultar(
        f"""
        SELECT cripto, extract_ts, price
        FROM {TABELA}
        WHERE cripto IN ({lista}) AND extract_ts > {limite_ms(janela_s)}
        ORDER BY extract_ts
        LIMIT 100000
        """
    )
    if df.empty:
        return df
    # O Pinot pode devolver TIMESTAMP como texto ou como epoch em ms
    if pd.api.types.is_numeric_dtype(df["extract_ts"]):
        df["extract_ts"] = pd.to_datetime(df["extract_ts"], unit="ms")
    else:
        df["extract_ts"] = pd.to_datetime(df["extract_ts"])
    df["price"] = df["price"].astype(float)
    return df


def buscar_variacoes(janela_s: int) -> pd.DataFrame:
    """Uma linha por moeda: primeiro e último preço, mínimo e máximo da janela."""
    df = consultar(
        f"""
        SELECT cripto,
               FIRST_WITH_TIME(price, extract_ts, 'DOUBLE') AS primeiro,
               LAST_WITH_TIME(price, extract_ts, 'DOUBLE') AS ultimo,
               MIN(price) AS minimo,
               MAX(price) AS maximo
        FROM {TABELA}
        WHERE extract_ts > {limite_ms(janela_s)}
        GROUP BY cripto
        LIMIT 1000
        """
    )
    if df.empty:
        return df
    for col in ["primeiro", "ultimo", "minimo", "maximo"]:
        df[col] = df[col].astype(float)
    df = df[(df["primeiro"] > 0) & (df["minimo"] > 0)].copy()
    df["variacao"] = (df["ultimo"] / df["primeiro"] - 1) * 100
    df["amplitude"] = (df["maximo"] / df["minimo"] - 1) * 100
    return df


def formatar_preco(valor: float) -> str:
    # Moedas como PEPE valem frações de centavo, então precisam de mais casas
    return f"{valor:,.2f}" if valor >= 1 else f"{valor:.8f}"


@st.fragment(run_every="10s")
def painel_mercado(janela_s: int, top_n: int, sem_stables: bool, tamanho: str):
    df = buscar_variacoes(janela_s)
    if sem_stables:
        df = df[~df["cripto"].isin(STABLES)]
    if df.empty:
        st.info("Sem dados nessa janela de tempo.")
        return

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Moedas monitoradas", len(df))
    k2.metric("Em alta", int((df["variacao"] > 0).sum()))
    k3.metric("Em queda", int((df["variacao"] < 0).sum()))
    k4.metric("Variação média", f"{df['variacao'].mean():+.2f}%")

    esq, dir_ = st.columns(2)

    # 1) Ranking de maiores altas e quedas
    destaques = pd.concat(
        [df.nlargest(top_n, "variacao"), df.nsmallest(top_n, "variacao")]
    ).drop_duplicates("cripto")
    destaques["sentido"] = destaques["variacao"].apply(lambda v: "Alta" if v >= 0 else "Queda")
    fig = px.bar(
        destaques, x="variacao", y="cripto", orientation="h", color="sentido",
        color_discrete_map={"Alta": VERDE, "Queda": VERMELHO},
    )
    fig.update_traces(texttemplate="%{x:+.2f}%")
    fig.update_yaxes(categoryorder="total ascending", title=None)
    fig.update_layout(title="Maiores altas e quedas (%)", showlegend=False,
                      xaxis_title=None, margin=MARGEM)
    esq.plotly_chart(fig)

    # 3) Mais voláteis (amplitude entre mínimo e máximo da janela)
    vol = df.nlargest(top_n, "amplitude")
    fig = px.bar(vol, x="amplitude", y="cripto", orientation="h",
                 color_discrete_sequence=[AZUL])
    fig.update_traces(texttemplate="%{x:.2f}%")
    fig.update_yaxes(categoryorder="total ascending", title=None)
    fig.update_layout(title="Mais voláteis: amplitude mín→máx (%)",
                      xaxis_title=None, margin=MARGEM)
    dir_.plotly_chart(fig)

    # 2) Mapa de calor do mercado
    mapa = df.copy()
    mapa["rotulo"] = (
        mapa["cripto"].str.replace("USDT", "", regex=False)
        + "<br>" + mapa["variacao"].map("{:+.2f}%".format)
    )
    mapa["peso"] = 1.0 if tamanho == "Iguais" else mapa["amplitude"].clip(lower=0.01)
    lim = max(mapa["variacao"].abs().max(), 0.01)
    fig = px.treemap(
        mapa, path=[px.Constant("Mercado"), "rotulo"], values="peso",
        color="variacao", color_continuous_scale="RdYlGn", range_color=[-lim, lim],
    )
    fig.update_traces(textposition="middle center")
    fig.update_layout(title="Mapa de calor: variação % no período", height=500,
                      margin=MARGEM, coloraxis_colorbar_title="%")
    st.plotly_chart(fig)

    st.caption(f"Atualizado às {pd.Timestamp.now('UTC'):%H:%M:%S} UTC")


@st.fragment(run_every="10s")
def painel_moedas(criptos: list[str], janela_s: int):
    df = buscar_precos(criptos, janela_s)
    if df.empty:
        st.info("Sem dados nessa janela de tempo.")
        return

    # Base 100 permite comparar moedas de escalas muito diferentes no mesmo gráfico
    base = df.copy()
    base["indice"] = base.groupby("cripto")["price"].transform(lambda s: s / s.iloc[0] * 100)
    fig = px.line(base, x="extract_ts", y="indice", color="cripto")
    fig.update_layout(title="Comparativo (base 100 no início da janela)",
                      xaxis_title=None, yaxis_title=None, margin=MARGEM)
    st.plotly_chart(fig)

    # Um gráfico por moeda: BTC e moedas baratas têm escalas incomparáveis
    for i in range(0, len(criptos), 3):
        colunas = st.columns(3)
        for col, cripto in zip(colunas, criptos[i : i + 3]):
            serie = df[df["cripto"] == cripto]
            if serie.empty:
                col.metric(cripto, "sem dados")
                continue
            ultimo, primeiro = serie["price"].iloc[-1], serie["price"].iloc[0]
            col.metric(cripto, formatar_preco(ultimo), f"{(ultimo / primeiro - 1) * 100:+.2f}% na janela")
            col.line_chart(serie, x="extract_ts", y="price", height=220)

    with st.expander("Últimos registros"):
        st.dataframe(df.sort_values("extract_ts", ascending=False).head(50))

    st.caption(f"Atualizado às {pd.Timestamp.now('UTC'):%H:%M:%S} UTC")


@st.fragment(run_every="30s")
def painel_correlacao(criptos: list[str], janela_s: int):
    df = buscar_precos(criptos, janela_s)
    if df.empty:
        st.info("Sem dados nessa janela de tempo.")
        return

    # Janelas curtas usam intervalos de 1 min, janelas longas de 5 min
    intervalo = "1min" if janela_s <= 60 * 60 else "5min"
    precos = df.pivot_table(
        index=df["extract_ts"].dt.floor(intervalo),
        columns="cripto", values="price", aggfunc="last",
    ).ffill()

    # Correlação de retornos, não de preços: séries em tendência correlacionam por acaso
    retornos = (precos / precos.shift(1) - 1).iloc[1:]
    retornos = retornos.loc[:, retornos.std() > 0].dropna(axis=1, thresh=5)
    if retornos.shape[1] < 2:
        st.info("Poucos dados para calcular a correlação. Aguarde alguns minutos ou aumente a janela.")
        return

    corr = retornos.corr()
    corr.index = corr.index.str.replace("USDT", "", regex=False)
    corr.columns = corr.columns.str.replace("USDT", "", regex=False)

    fig = px.imshow(corr, text_auto=".2f", color_continuous_scale="RdBu_r", zmin=-1, zmax=1)
    fig.update_layout(title=f"Correlação dos retornos ({intervalo}) entre as moedas",
                      height=560, margin=MARGEM)
    st.plotly_chart(fig)

    pares = corr.where(np.triu(np.ones(corr.shape, dtype=bool), k=1)).stack()
    maior, menor = pares.idxmax(), pares.idxmin()
    c1, c2 = st.columns(2)
    c1.metric("Mais correlacionadas", f"{maior[0]} × {maior[1]}", f"{pares.max():+.2f}", delta_color="off")
    c2.metric("Menos correlacionadas", f"{menor[0]} × {menor[1]}", f"{pares.min():+.2f}", delta_color="off")
    st.caption(f"{len(retornos)} intervalos de {intervalo} · atualizado às {pd.Timestamp.now('UTC'):%H:%M:%S} UTC")


st.title("Cotações de criptomoedas em tempo real")
st.caption("Binance API → Kafka → Pinot → Streamlit · horários em UTC")

with st.sidebar:
    st.header("Filtros")
    janela = st.selectbox("Janela de tempo", list(JANELAS), index=1)
    top_n = st.slider("Itens nos rankings", 3, 20, 10)
    sem_stables = st.checkbox("Ocultar stablecoins", value=True)
    tamanho = st.radio("Tamanho dos blocos do mapa", ["Iguais", "Por volatilidade"])
    st.divider()
    disponiveis = listar_criptos()
    selecionadas = st.multiselect(
        "Moedas em destaque", disponiveis,
        default=[c for c in PADRAO if c in disponiveis], max_selections=6,
    )

aba_mercado, aba_moedas, aba_corr = st.tabs(
    ["Visão do mercado", "Moedas selecionadas", "Correlação"]
)

with aba_mercado:
    painel_mercado(JANELAS[janela], top_n, sem_stables, tamanho)

with aba_moedas:
    if selecionadas:
        painel_moedas(selecionadas, JANELAS[janela])
    else:
        st.warning("Selecione ao menos uma moeda na barra lateral.")

with aba_corr:
    criptos_corr = st.multiselect(
        "Moedas na matriz", disponiveis,
        default=[c for c in PADRAO_CORR if c in disponiveis],
        max_selections=20, key="moedas_corr",
    )
    if len(criptos_corr) >= 2:
        painel_correlacao(criptos_corr, JANELAS[janela])
    else:
        st.warning("Selecione ao menos 2 moedas para calcular a correlação.")