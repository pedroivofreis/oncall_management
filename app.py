import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import uuid
import time

st.set_page_config(page_title="Gestão OnCall", layout="wide", page_icon="💸")

# --- 1. CONEXÃO ---
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error(f"Erro de Conexão: {e}")
    st.stop()

# --- 2. CARREGAMENTO ---
try:
    df_config = conn.read(worksheet="config", ttl=0)
    df_lancamentos = conn.read(worksheet="lancamentos", ttl=0)
except:
    df_config = pd.DataFrame(columns=["projetos", "emails_autorizados", "valor_hora"])
    df_lancamentos = pd.DataFrame(columns=["id", "data_registro", "competencia", "colaborador_email", "projeto", "horas", "descricao", "status_aprovaca", "data_decisao"])

# Tratamento de dados antigos
if "competencia" not in df_lancamentos.columns:
    df_lancamentos["competencia"] = ""

mask_vazia = df_lancamentos["competencia"].isna() | (df_lancamentos["competencia"] == "")
if mask_vazia.any():
    datas_temp = pd.to_datetime(df_lancamentos.loc[mask_vazia, "data_registro"], errors='coerce')
    df_lancamentos.loc[mask_vazia, "competencia"] = datas_temp.dt.strftime("%Y-%m")
    df_lancamentos["competencia"] = df_lancamentos["competencia"].fillna(datetime.now().strftime("%Y-%m"))

df_lancamentos["status_aprovaca"] = df_lancamentos["status_aprovaca"].fillna("Pendente").replace("", "Pendente")

# --- 3. VARIÁVEIS ---
try:
    user_email = st.user.email
    if user_email is None: raise Exception()
except:
    user_email = "pedroivofernandesreis@gmail.com"

ADMINS = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]

lista_projetos = df_config["projetos"].dropna().unique().tolist()
if not lista_projetos: lista_projetos = ["Sistema de horas", "Outros"]

try:
    valor_hora_padrao = float(df_config["valor_hora"].dropna().iloc[0])
except:
    valor_hora_padrao = 100.0

# --- 4. ACESSO ---
if user_email not in ADMINS and user_email not in df_config["emails_autorizados"].values:
    st.error(f"🔒 Acesso negado para {user_email}.")
    st.stop()

# --- 5. INTERFACE ---
st.title("🚀 Gestão OnCall")

tabs_list = ["📝 Lançar"]
if user_email in ADMINS:
    tabs_list += ["🛡️ Painel da Clau", "📊 BI & Financeiro", "⚙️ Config"]

abas = st.tabs(tabs_list)

# === ABA 1: LANÇAR ===
with abas[0]:
    st.caption(f"Logado como: {user_email}")
    with st.form("form_lan", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        proj = c1.selectbox("Projeto", lista_projetos)
        hor = c2.number_input("Horas", min_value=0.5, step=0.5, format="%.1f")
        comp_atual = datetime.now().strftime("%Y-%m")
        c3.text_input("Competência", value=comp_atual, disabled=True)
        desc = st.text_area("Descrição da atividade")
        
        if st.form_submit_button("Enviar Registro"):
            novo = pd.DataFrame([{
                "id": str(uuid.uuid4()),
                "data_registro": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "competencia": comp_atual,
                "colaborador_email": user_email,
                "projeto": proj,
                "horas": hor,
                "descricao": desc,
                "status_aprovaca": "Pendente",
                "data_decisao": ""
            }])
            final = pd.concat([df_lancamentos, novo], ignore_index=True).astype(str)
            conn.update(worksheet="lancamentos", data=final)
            st.success("Sucesso! Registro enviado.")
            st.rerun()

# === ÁREA ADMIN ===
if user_email in ADMINS:
    
    # ABA 2: PAINEL DA CLAU (COM IMPORTADOR)
    with abas[1]:
        st.subheader("🛡️ Central de Controle")
        
        # --- IMPORTADOR DE EXCEL ---
        with st.expander("📥 Importar Excel Retroativo (Clique para abrir)"):
            st.info("Suba a planilha padrão. O sistema lê: Colaborador (B1), Data, Descrição e Horas.")
            arquivo = st.file_uploader("Selecione o arquivo .xlsx", type=["xlsx"])
            
            if arquivo:
                try:
                    # Lê o cabeçalho para pegar o email
                    # header=None para ler a célula B1 crua
                    df_header = pd.read_excel(arquivo, header=None, nrows=2)
                    email_colab = str(df_header.iloc[0, 1]).strip() # Célula B1
                    
                    if "@" not in email_colab:
                        st.error("⚠️ Não encontrei um e-mail válido na célula B1 (Profissional). Verifique a planilha.")
                    else:
                        # Lê os dados a partir da linha 4 (cabeçalho da tabela)
                        df_excel = pd.read_excel(arquivo, header=4)
                        
                        # Filtra linhas vazias (onde Data ou Descrição estão vazios)
                        df_excel = df_excel.dropna(subset=["Data", "Descrição"])
                        
                        st.write(f"**Colaborador detectado:** {email_colab}")
                        st.write(f"**Registros encontrados:** {len(df_excel)}")
                        
                        if st.button("🚀 Processar Importação"):
                            novos_registros = []
                            for index, row in df_excel.iterrows():
                                # Converte Horas (Excel pode vir como 06:00:00 datetime ou float)
                                try:
                                    raw_horas = row["Horas"]
                                    if isinstance(raw_horas, datetime) or hasattr(raw_horas, 'hour'):
                                        # Se for objeto de tempo (06:00:00)
                                        horas_float = raw_horas.hour + (raw_horas.minute / 60)
                                    else:
                                        # Se for string ou numero
                                        horas_float = float(str(raw_horas).replace(",", "."))
                                except:
                                    horas_float = 0.0

                                # Pula se horas for zero
                                if horas_float <= 0: continue
                                
                                # Data e Competência
                                data_real = pd.to_datetime(row["Data"], errors='coerce')
                                if pd.isna(data_real): continue # Pula data inválida
                                
                                novos_registros.append({
                                    "id": str(uuid.uuid4()),
                                    "data_registro": data_real.strftime("%Y-%m-%d %H:%M:%S"),
                                    "competencia": data_real.strftime("%Y-%m"),
                                    "colaborador_email": email_colab,
                                    "projeto": "Outros", # Padrão para importação
                                    "horas": horas_float,
                                    "descricao": str(row["Descrição"]),
                                    "status_aprovaca": "Aprovado", # Já entra aprovado
                                    "data_decisao": datetime.now().strftime("%Y-%m-%d")
                                })
                            
                            if novos_registros:
                                df_novos = pd.DataFrame(novos_registros)
                                df_final_import = pd.concat([df_lancamentos, df_novos], ignore_index=True).astype(str)
                                conn.update(worksheet="lancamentos", data=df_final_import)
                                st.success(f"Importação concluída! {len(novos_registros)} registros adicionados.")
                                time.sleep(2)
                                st.rerun()
                            else:
                                st.warning("Nenhum registro válido (com horas > 0) encontrado.")
                except Exception as e:
                    st.error(f"Erro ao ler arquivo: {e}")

        st.divider()
        st.markdown("#### 📝 Edição de Registros")
        
        # Editor completo
        edited_df = st.data_editor(
            df_lancamentos,
            column_config={
                "status_aprovaca": st.column_config.SelectboxColumn("Status", options=["Pendente", "Aprovado", "Rejeitado"], required=True),
                "competencia": st.column_config.TextColumn("Competência (AAAA-MM)"),
                "horas": st.column_config.NumberColumn("Horas", min_value=0, step=0.5),
                "projeto": st.column_config.SelectboxColumn("Projeto", options=lista_projetos),
                "data_registro": st.column_config.TextColumn("Data Real", disabled=True)
            },
            disabled=["id", "colaborador_email"], 
            hide_index=True,
            num_rows="dynamic"
        )
        
        if st.button("💾 Salvar Alterações"):
            for i, row in edited_df.iterrows():
                if row["status_aprovaca"] != "Pendente" and (pd.isna(row["data_decisao"]) or row["data_decisao"] == ""):
                    edited_df.at[i, "data_decisao"] = datetime.now().strftime("%Y-%m-%d")
            conn.update(worksheet="lancamentos", data=edited_df.astype(str))
            st.success("Atualizado!")
            st.rerun()

    # ABA 3: DASHBOARD
    with abas[2]:
        st.subheader("📊 Inteligência Financeira")
        
        df_bi = df_lancamentos.copy()
        df_bi["horas"] = pd.to_numeric(df_bi["horas"], errors="coerce").fillna(0)
        
        col_filtro, col_kpi = st.columns([1, 3])
        with col_filtro:
            opcoes_mes = sorted([x for x in df_bi["competencia"].unique().tolist() if x], reverse=True)
            if not opcoes_mes: opcoes_mes = [datetime.now().strftime("%Y-%m")]
            mes_sel = st.selectbox("📅 Competência", ["TODOS"] + opcoes_mes)
        
        if mes_sel != "TODOS":
            df_view = df_bi[df_bi["competencia"] == mes_sel]
        else:
            df_view = df_bi
            
        aprovados = df_view[df_view["status_aprovaca"] == "Aprovado"]
        total_h = aprovados["horas"].sum()
        total_rs = total_h * valor_hora_padrao
        
        with col_kpi:
            k1, k2, k3 = st.columns(3)
            k1.metric("Horas Aprovadas", f"{total_h:.1f}h")
            k2.metric("Total a Pagar", f"R$ {total_rs:,.2f}")
            k3.metric("Lançamentos Aprovados", len(aprovados))
        
        st.divider()
        
        c_bi1, c_bi2 = st.columns(2)
        with c_bi1:
            st.markdown("### 👥 Por Colaborador")
            if not aprovados.empty:
                fechamento = aprovados.groupby("colaborador_email").agg(Horas=("horas", "sum")).reset_index()
                fechamento["A Pagar"] = fechamento["Horas"] * valor_hora_padrao
                st.dataframe(fechamento, hide_index=True, use_container_width=True)
        with c_bi2:
            st.markdown("### 🏗️ Custo por Projeto")
            if not aprovados.empty:
                st.bar_chart(aprovados.groupby("projeto")["horas"].sum() * valor_hora_padrao)

    # ABA 4: CONFIG
    with abas[3]:
        st.subheader("Configurações")
        conf_edit = st.data_editor(df_config, num_rows="dynamic")
        if st.button("Salvar Configurações"):
            conn.update(worksheet="config", data=conf_edit.astype(str))
            st.success("Salvo!")