import os
import io
import base64
import bcrypt
import requests
import streamlit as st
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
import pytz
from dotenv import load_dotenv

load_dotenv()

EVOLUTION_URL       = os.getenv("EVOLUTION_URL", "")
EVOLUTION_KEY       = os.getenv("EVOLUTION_KEY", "")
INSTANCE_NAME       = os.getenv("INSTANCE_NAME", "")
APP_USERNAME        = os.getenv("APP_USERNAME", "admin")
APP_PASSWORD_HASH   = os.getenv("APP_PASSWORD_HASH", "")

# ── Autenticação ────────────────────────────────────────────────────────────────
def check_password(username: str, password: str) -> bool:
    if username != APP_USERNAME:
        return False
    if not APP_PASSWORD_HASH:
        return False
    return bcrypt.checkpw(password.encode(), APP_PASSWORD_HASH.encode())

def login_screen():
    st.set_page_config(page_title="Login", page_icon="🔒", layout="centered")
    st.title("🔒 Login")
    with st.form("login_form"):
        username = st.text_input("Usuário")
        password = st.text_input("Senha", type="password")
        submitted = st.form_submit_button("Entrar", use_container_width=True)
        if submitted:
            if check_password(username, password):
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("Usuário ou senha incorretos.")

if not st.session_state.get("authenticated"):
    login_screen()
    st.stop()

# ── Helpers Evolution API ───────────────────────────────────────────────────────
def _headers():
    return {"apikey": EVOLUTION_KEY, "Content-Type": "application/json"}

def api_status():
    r = requests.get(
        f"{EVOLUTION_URL}/instance/fetchInstances",
        headers=_headers(), timeout=10
    )
    r.raise_for_status()
    instances = r.json()
    # a v2.3.x retorna lista; cada item pode ter formatos diferentes
    for inst in instances:
        inner = inst.get("instance", inst)
        name  = inner.get("instanceName") or inner.get("name", "")
        if name == INSTANCE_NAME:
            state = (
                inner.get("state")
                or inner.get("status")
                or inst.get("state")
                or inst.get("status")
                or inst.get("connectionStatus")
                or inner.get("connectionStatus")
            )
            return state or "desconhecido", inst  # retorna estado + raw pra debug
    return "não encontrada", {}

def api_connect():
    r = requests.get(
        f"{EVOLUTION_URL}/instance/connect/{INSTANCE_NAME}",
        headers=_headers(), timeout=15
    )
    r.raise_for_status()
    return r.json()

def api_logout():
    r = requests.delete(
        f"{EVOLUTION_URL}/instance/logout/{INSTANCE_NAME}",
        headers=_headers(), timeout=15
    )
    r.raise_for_status()
    return r.json()

def api_restart():
    r = requests.put(
        f"{EVOLUTION_URL}/instance/restart/{INSTANCE_NAME}",
        headers=_headers(), timeout=15
    )
    r.raise_for_status()
    return r.json()

# ── Saudação por horário ────────────────────────────────────────────────────────
def get_saudacao():
    hora = datetime.now(pytz.timezone("America/Sao_Paulo")).hour
    if 5 <= hora < 12:
        return "Bom dia"
    elif 12 <= hora < 18:
        return "Boa tarde"
    return "Boa noite"

# ── Gera imagem PNG da tabela ───────────────────────────────────────────────────
def gerar_imagem_tabela(df: pd.DataFrame, nome_engenheiro: str) -> bytes:
    colunas = [c for c in df.columns if c not in ("Engenheiro", "Email", "Telefone")]
    df_img = df[colunas].copy()

    for col in df_img.columns:
        if pd.api.types.is_numeric_dtype(df_img[col]):
            df_img[col] = df_img[col].apply(lambda v: f"{v:.1f}" if pd.notna(v) else "")

    total_row = {}
    for col in df_img.columns:
        if col == "Vol.Carteira":
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
             "/usr/share/fonts/dejavu/DejaVuSans.ttf", "arial.ttf"]
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
    title_h  = 48
    total_h  = title_h + HEADER_H + ROW_H * len(df_img) + TOTAL_H + 4

    img  = Image.new("RGB", (total_w, total_h), "#1e293b")
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, total_w, title_h], fill="#0f172a")
    draw.text((PADDING, 12), f"Obras - {nome_engenheiro}", font=font_title, fill="#ffffff")

    x, y = 0, title_h
    draw.rectangle([0, y, total_w, y + HEADER_H], fill="#0f172a")
    for i, col in enumerate(df_img.columns):
        draw.text((x + PADDING, y + 10), str(col), font=font_header, fill="#ffffff")
        x += col_widths[i]

    for r_idx, (_, row) in enumerate(df_img.iterrows()):
        y = title_h + HEADER_H + r_idx * ROW_H
        bg = "#263548" if r_idx % 2 == 0 else "#1e293b"
        draw.rectangle([0, y, total_w, y + ROW_H], fill=bg)
        x = 0
        for c_idx, val in enumerate(row.astype(str)):
            draw.text((x + PADDING, y + 9), val, font=font_body, fill="#e2e8f0")
            x += col_widths[c_idx]

    y_total = title_h + HEADER_H + ROW_H * len(df_img)
    draw.rectangle([0, y_total, total_w, y_total + TOTAL_H], fill="#1e40af")
    x = 0
    for c_idx, col in enumerate(df_total.columns):
        draw.text((x + PADDING, y_total + 11), str(df_total[col].iloc[0]), font=font_total, fill="#ffffff")
        x += col_widths[c_idx]

    x = 0
    for w in col_widths[:-1]:
        x += w
        draw.line([(x, title_h), (x, total_h)], fill="#334155", width=1)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

# ── Envios ──────────────────────────────────────────────────────────────────────
def enviar_texto(telefone: str, mensagem: str):
    r = requests.post(
        f"{EVOLUTION_URL}/message/sendText/{INSTANCE_NAME}",
        json={"number": telefone, "text": mensagem},
        headers=_headers(), timeout=15
    )
    r.raise_for_status()
    return r.json()

def enviar_imagem(telefone: str, img_bytes: bytes, caption: str):
    r = requests.post(
        f"{EVOLUTION_URL}/message/sendMedia/{INSTANCE_NAME}",
        data={"number": telefone, "mediatype": "image", "caption": caption},
        files={"file": ("tabela.png", img_bytes, "image/png")},
        headers={"apikey": EVOLUTION_KEY},
        timeout=30
    )
    r.raise_for_status()
    return r.json()

# ── App ─────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Envio para Engenheiros", page_icon="👷", layout="wide")

col_title, col_logout = st.columns([6, 1])
with col_title:
    st.title("👷 Envio de Obras para Engenheiros")
with col_logout:
    st.write("")
    if st.button("Sair", use_container_width=True):
        st.session_state["authenticated"] = False
        st.rerun()

aba_envio, aba_whatsapp = st.tabs(["📤 Envio de Obras", "📱 WhatsApp"])

# ════════════════════════════════════════════════════════════════════════════════
# ABA 1 — Envio de Obras
# ════════════════════════════════════════════════════════════════════════════════
with aba_envio:
    arquivo = st.file_uploader("Selecione a planilha XLSX", type=["xlsx"])

    if arquivo:
        df = pd.read_excel(arquivo)
        st.success(f"{len(df)} linhas carregadas")

        engenheiros = df["Engenheiro"].dropna().unique().tolist()
        st.info(f"**{len(engenheiros)} engenheiros encontrados:** {', '.join(engenheiros)}")

        preview_eng = st.selectbox("Preview da tabela por engenheiro", engenheiros)
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
            status   = st.empty()

            for i, eng in enumerate(engenheiros):
                df_eng = df[df["Engenheiro"] == eng]
                telefone = "55" + "".join(filter(str.isdigit, str(df_eng["Telefone"].iloc[0])))
                status.write(f"Enviando para **{eng}** ({telefone})...")
                try:
                    enviar_texto(telefone, f"{saudacao}, {eng}! 👷\n\nSegue o resumo das suas obras:")
                    enviar_imagem(telefone, gerar_imagem_tabela(df_eng, eng), "Tabela de obras atualizada 📋")
                    st.success(f"✅ {eng} — enviado")
                except Exception as e:
                    st.error(f"❌ {eng} — erro: {e}")
                progress.progress((i + 1) / len(engenheiros))

            status.write("✅ Concluído!")

# ════════════════════════════════════════════════════════════════════════════════
# ABA 2 — WhatsApp / Evolution API
# ════════════════════════════════════════════════════════════════════════════════
with aba_whatsapp:
    if not EVOLUTION_URL or not EVOLUTION_KEY or not INSTANCE_NAME:
        st.error("⚠️ Variáveis de ambiente não configuradas. Adicione EVOLUTION_URL, EVOLUTION_KEY e INSTANCE_NAME no Easypanel (Environment).")
        st.stop()

    st.subheader(f"Instância: `{INSTANCE_NAME}`")
    st.divider()

    col_status, col_qr = st.columns([1, 1])

    with col_status:
        st.markdown("**Status da conexão**")
        if st.button("🔄 Verificar status"):
            try:
                estado, raw = api_status()
                cor = "🟢" if estado == "open" else ("🟡" if estado in ("connecting", "qrcode") else "🔴")
                st.metric("Status", f"{cor} {estado}")
                if estado == "desconhecido":
                    st.json(raw)
            except Exception as e:
                st.error(f"Erro ao verificar: {e}")

    with col_qr:
        st.markdown("**Conectar WhatsApp**")
        if st.button("📲 Gerar QR Code"):
            try:
                resp = api_connect()
                qr_base64 = (
                    resp.get("base64")
                    or resp.get("qrcode", {}).get("base64")
                    or resp.get("code")
                )
                if qr_base64:
                    qr_bytes = base64.b64decode(qr_base64.split(",")[-1])
                    st.image(qr_bytes, caption="Escaneie no WhatsApp", width=280)
                else:
                    st.info("Instância já conectada ou QR não disponível.")
                    st.json(resp)
            except Exception as e:
                st.error(f"Erro ao conectar: {e}")
