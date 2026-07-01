import streamlit as st
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
import io
import requests
from datetime import datetime
import pytz

# ── Configuração da Evolution API ──────────────────────────────────────────────
EVOLUTION_URL = "https://evolutionapi.devlopplay.site"   # troque pela URL da sua Evolution API
EVOLUTION_KEY = "7899B96784EA-4026-91B6-E8FAE5F44539"            # troque pela sua API Key
INSTANCE_NAME = "Macbook"                # troque pelo nome da sua instância

# ── Saudação por horário ────────────────────────────────────────────────────────
def get_saudacao():
    hora = datetime.now(pytz.timezone("America/Sao_Paulo")).hour
    if 5 <= hora < 12:
        return "Bom dia"
    elif 12 <= hora < 18:
        return "Boa tarde"
    return "Boa noite"

# ── Gera imagem PNG da tabela do engenheiro ─────────────────────────────────────
def gerar_imagem_tabela(df: pd.DataFrame, nome_engenheiro: str) -> bytes:
    colunas = [c for c in df.columns if c not in ("Engenheiro", "Email", "Telefone")]
    df_img = df[colunas].copy()

    # formata colunas numéricas com 1 casa decimal
    for col in df_img.columns:
        if pd.api.types.is_numeric_dtype(df_img[col]):
            df_img[col] = df_img[col].apply(lambda v: f"{v:.1f}" if pd.notna(v) else "")

    # monta linha de total (soma só colunas numéricas originais)
    total_row = {}
    numeric_cols = [c for c in df[colunas].columns if pd.api.types.is_numeric_dtype(df[c])]
    for col in df_img.columns:
        if col in numeric_cols:
            total_row[col] = f"{df[col].sum():.1f}"
        elif col == df_img.columns[0]:
            total_row[col] = "TOTAL"
        else:
            total_row[col] = ""
    df_total = pd.DataFrame([total_row])

    PADDING = 16
    HEADER_H = 44
    ROW_H = 36
    TOTAL_H = 40
    FONT_SIZE = 16

    def load_font(bold=False, size=FONT_SIZE):
        candidates = (
            ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
             "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"]
            if bold else
            ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
             "/usr/share/fonts/dejavu/DejaVuSans.ttf",
             "arial.ttf"]
        )
        for path in candidates:
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
        return ImageFont.load_default()

    font_header = load_font(bold=True)
    font_body   = load_font()
    font_title  = load_font(bold=True, size=18)
    font_total  = load_font(bold=True)

    # calcula largura de cada coluna (considera dados + linha de total)
    dummy = Image.new("RGB", (1, 1))
    draw_dummy = ImageDraw.Draw(dummy)
    col_widths = []
    for col in df_img.columns:
        max_w = draw_dummy.textlength(str(col), font=font_header)
        for val in list(df_img[col].astype(str)) + list(df_total[col].astype(str)):
            w = draw_dummy.textlength(val, font=font_body)
            if w > max_w:
                max_w = w
        col_widths.append(int(max_w) + PADDING * 2)

    total_w = sum(col_widths)
    title_h = 48
    total_h = title_h + HEADER_H + ROW_H * len(df_img) + TOTAL_H + 4

    img = Image.new("RGB", (total_w, total_h), "#1e293b")
    draw = ImageDraw.Draw(img)

    # título
    draw.rectangle([0, 0, total_w, title_h], fill="#0f172a")
    draw.text((PADDING, 12), f"Obras - {nome_engenheiro}", font=font_title, fill="#ffffff")

    # cabeçalho
    x = 0
    y = title_h
    draw.rectangle([0, y, total_w, y + HEADER_H], fill="#0f172a")
    for i, col in enumerate(df_img.columns):
        draw.text((x + PADDING, y + 10), str(col), font=font_header, fill="#ffffff")
        x += col_widths[i]

    # linhas de dados
    for r_idx, (_, row) in enumerate(df_img.iterrows()):
        y = title_h + HEADER_H + r_idx * ROW_H
        bg = "#263548" if r_idx % 2 == 0 else "#1e293b"
        draw.rectangle([0, y, total_w, y + ROW_H], fill=bg)
        x = 0
        for c_idx, val in enumerate(row.astype(str)):
            draw.text((x + PADDING, y + 9), val, font=font_body, fill="#e2e8f0")
            x += col_widths[c_idx]

    # linha de total
    y_total = title_h + HEADER_H + ROW_H * len(df_img)
    draw.rectangle([0, y_total, total_w, y_total + TOTAL_H], fill="#1e40af")
    x = 0
    for c_idx, col in enumerate(df_total.columns):
        val = str(df_total[col].iloc[0])
        draw.text((x + PADDING, y_total + 11), val, font=font_total, fill="#ffffff")
        x += col_widths[c_idx]

    # bordas separadoras entre colunas
    x = 0
    for w in col_widths[:-1]:
        x += w
        draw.line([(x, title_h), (x, total_h)], fill="#334155", width=1)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

# ── Envia mensagem de texto via Evolution API ───────────────────────────────────
def enviar_texto(telefone: str, mensagem: str):
    url = f"{EVOLUTION_URL}/message/sendText/{INSTANCE_NAME}"
    payload = {"number": telefone, "text": mensagem}
    headers = {"apikey": EVOLUTION_KEY, "Content-Type": "application/json"}
    r = requests.post(url, json=payload, headers=headers, timeout=15)
    r.raise_for_status()
    return r.json()

# ── Envia imagem via Evolution API (v2.3.7 — multipart) ────────────────────────
def enviar_imagem(telefone: str, img_bytes: bytes, caption: str):
    url = f"{EVOLUTION_URL}/message/sendMedia/{INSTANCE_NAME}"
    headers = {"apikey": EVOLUTION_KEY}
    files = {"file": ("tabela.png", img_bytes, "image/png")}
    data = {
        "number": telefone,
        "mediatype": "image",
        "caption": caption,
    }
    r = requests.post(url, data=data, files=files, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()

# ── Interface Streamlit ─────────────────────────────────────────────────────────
st.set_page_config(page_title="Envio para Engenheiros", page_icon="👷", layout="wide")
st.title("👷 Envio de Obras para Engenheiros")

arquivo = st.file_uploader("Selecione a planilha XLSX", type=["xlsx"])

if arquivo:
    df = pd.read_excel(arquivo)
    st.success(f"{len(df)} linhas carregadas")

    engenheiros = df["Engenheiro"].dropna().unique().tolist()
    st.info(f"**{len(engenheiros)} engenheiros encontrados:** {', '.join(engenheiros)}")

    col1, col2 = st.columns(2)
    with col1:
        preview_eng = st.selectbox("Preview da tabela por engenheiro", engenheiros)
    with col2:
        st.write("")

    if preview_eng:
        df_eng = df[df["Engenheiro"] == preview_eng]
        st.dataframe(df_eng, use_container_width=True)
        img_bytes = gerar_imagem_tabela(df_eng, preview_eng)
        st.image(img_bytes, caption=f"Imagem que será enviada — {preview_eng}")

    st.divider()
    st.subheader("Disparar mensagens")

    if st.button("🚀 Enviar para todos os engenheiros", type="primary"):
        saudacao = get_saudacao()
        progress = st.progress(0)
        status = st.empty()

        for i, eng in enumerate(engenheiros):
            df_eng = df[df["Engenheiro"] == eng]
            telefone_raw = str(df_eng["Telefone"].iloc[0])
            telefone = "55" + "".join(filter(str.isdigit, telefone_raw))

            status.write(f"Enviando para **{eng}** ({telefone})...")

            try:
                enviar_texto(telefone, f"{saudacao}, {eng}! 👷\n\nSegue o resumo das suas obras:")
                img_bytes = gerar_imagem_tabela(df_eng, eng)
                enviar_imagem(telefone, img_bytes, "Tabela de obras atualizada 📋")
                st.success(f"✅ {eng} — enviado")
            except Exception as e:
                st.error(f"❌ {eng} — erro: {e}")

            progress.progress((i + 1) / len(engenheiros))

        status.write("✅ Concluído!")
