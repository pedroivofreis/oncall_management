import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import uuid
import time

st.set_page_config(page_title="Gestão OnCall", layout="wide", page_icon="🚀")

# --- 1. CONEXÃO ---
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error(f"Erro de Conexão: {e}")
    st.stop()

# --- 2. CARREGAMENTO DOS DADOS ---
# ttl=0 garante que estamos vendo a verdade nua e crua da planilha
try:
    df_config = conn.read(worksheet="config", ttl=0)
    df_lancamentos = conn.read(worksheet="lancamentos", ttl=0)
except:
    # Fallback se der erro na leitura
    df_config = pd.DataFrame(columns=["projetos", "emails_autorizados", "valor_hora"])
    df_lancamentos = pd.DataFrame(columns=["id", "data_registro", "competencia", "colaborador_email", "projeto", "tipo", "horas", "descricao", "status_aprovaca", "data_decisao"])

# --- 3. TRATAMENTO / MIGRAÇÃO (PARA DADOS ANTIGOS) ---
if "competencia" not in df_lancamentos.columns: df_lancamentos["competencia"] = ""
if "tipo" not in df_lancamentos.columns: df_lancamentos["tipo"] = "Geral"

# Corrige competências vazias
mask_vazia = df_lancamentos["competencia"].isna() | (df_lancamentos["competencia"] == "") | (df_lancamentos["competencia"] == "nan")
if mask_vazia.any():
    datas_temp = pd.to_datetime(df_lancamentos.loc[mask_vazia, "data_registro"], errors='coerce')
    df_lancamentos.loc[mask_vazia, "competencia"] = datas_temp.dt.strftime("%Y-%m")
    df_lancamentos["competencia"] = df_lancamentos["competencia"].fillna(datetime.now().strftime("%Y-%m"))

df_lancamentos["status_aprovaca"] = df_lancamentos["status_aprovaca"].fillna("Pendente").replace("", "Pendente")
df_lancamentos["tipo"] = df_lancamentos["tipo"].fillna("Geral").replace("nan", "Geral")

# --- 4. PREPARAÇÃO DAS LISTAS DE CONFIGURAÇÃO ---
# (Essa parte é crucial para o salvamento correto)
try:
    # Projetos
    raw_proj = df_config["projetos"].unique().tolist()
    lista_projetos = [str(x).strip() for x in raw_proj if x and str(x).lower() not in ["nan", "none", "", "0"]]
    if not lista_projetos: lista_projetos = ["Sistema de horas"]

    # Emails
    raw_email = df_config["emails_autorizados"].unique().tolist()
    lista_emails = [str(x).strip() for x in raw_email if x and str(x).lower() not in ["nan", "none", "", "0"] and "@" in str(x)]
    
    # Valor Hora
    try:
        valor_hora_padrao = float(df_config["valor_hora"].dropna().iloc[0])
    except:
        valor_hora_padrao = 100.0
except Exception as e:
    st.error(f"Erro ao processar configurações: {e}")
    st.stop()

# --- 5. CONTROLE DE ACESSO ---
try:
    user_email = st.user.email
    if user_email is None: raise Exception()
except:
    user_email = "pedroivofernandesreis@gmail.com"

ADMINS = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]

if user_email not in ADMINS and user_email not in lista_emails:
    st.error(f"🔒 Acesso negado para {user_email}. Peça para um admin te cadastrar na aba Configurações.")
    st.stop()

# --- 6. INTERFACE ---
st.title("🚀 Gestão OnCall")

tabs_list = ["📝 Lançar"]
if user_email in ADMINS:
    tabs_list += ["🛡️ Painel da Clau", "📊 BI & Financeiro", "⚙️ Configurações"]

abas = st.tabs(tabs_list)

# === ABA 1: LANÇAR ===
with abas[0]:
    st.caption(f"Logado como: {user_email}")
    with st.form("form_lan", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        proj = c1.selectbox("Projeto", lista_projetos)
        tipo_ativ = c2.selectbox("Tipo", ["Front-end", "Back-end", "Banco de Dados", "Infraestrutura", "Reunião", "Outros"])
        hor = c3.number_input("Horas", min_value=0.5, step=0.5, format="%.1f")
        
        c4, c5 = st.columns([1, 2])
        comp_atual = datetime.now().strftime("%Y-%m")
        c4.text_input("Competência", value=comp_atual, disabled=True)
        desc = c5.text_area("Descrição")
        
        if st.form_submit_button("Enviar Registro"):
            novo = pd.DataFrame([{
                "id": str(uuid.uuid4()),
                "data_registro": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "competencia": comp_atual,
                "colaborador_email": user_email,
                "projeto": proj,
                "tipo": tipo_ativ,
                "horas": hor,
                "descricao": desc,
                "status_aprovaca": "Pendente",
                "data_decisao": ""
            }])
            final = pd.concat([df_lancamentos, novo], ignore_index=True).astype(str)
            conn.update(worksheet="lancamentos", data=final)
            st.success("✅ Registro salvo com sucesso!")
            st.rerun()

# === ÁREA ADMIN ===
if user_email in ADMINS:
    
    # ABA 2: PAINEL DA CLAU
    with abas[1]:
        st.subheader("🛡️ Central de Controle")
        
        # IMPORTADOR
        with st.expander("📥 Importar Excel Retroativo"):
            arquivo = st.file_uploader("Arquivo .xlsx", type=["xlsx"])
            if arquivo and st.button("Processar Importação"):
                try:
                    df_h = pd.read_excel(arquivo, header=None, nrows=2)
                    email_c = str(df_h.iloc[0, 1]).strip()
                    if "@" in email_c:
                        df_x = pd.read_excel(arquivo, header=4).dropna(subset=["Data", "Descrição"])
                        novos = []
                        for _, row in df_x.iterrows():
                            try:
                                h = row["Horas"]
                                h_f = h.hour + (h.minute/60) if hasattr(h, 'hour') else float(str(h).replace(",", "."))
                            except: h_f = 0.0
                            if h_f > 0:
                                d = pd.to_datetime(row["Data"], errors='coerce')
                                if not pd.isna(d):
                                    novos.append({
                                        "id": str(uuid.uuid4()),
                                        "data_registro": d.strftime("%Y-%m-%d %H:%M:%S"),
                                        "competencia": d.strftime("%Y-%m"),
                                        "colaborador_email": email_c,
                                        "projeto": "Outros", "tipo": "Geral", "horas": h_f,
                                        "descricao": str(row["Descrição"]), "status_aprovaca": "Aprovado",
                                        "data_decisao": datetime.now().strftime("%Y-%m-%d")
                                    })
                        if novos:
                            conn.update(worksheet="lancamentos", data=pd.concat([df_lancamentos, pd.DataFrame(novos)], ignore_index=True).astype(str))
                            st.success(f"{len(novos)} importados!")
                            time.sleep(1); st.rerun()
                except Exception as e: st.error(f"Erro: {e}")

        # EDITOR GERAL
        st.divider()
        st.write("#### 📝 Edição Geral")
        edited_df = st.data_editor(
            df_lancamentos,
            column_config={
                "status_aprovaca": st.column_config.SelectboxColumn("Status", options=["Pendente", "Aprovado", "Rejeitado"], required=True),
                "projeto": st.column_config.SelectboxColumn("Projeto", options=lista_projetos),
                "tipo": st.column_config.SelectboxColumn("Tipo", options=["Front-end", "Back-end", "Banco de Dados", "Infraestrutura", "Reunião", "Outros"]),
                "data_registro": st.column_config.TextColumn("Data", disabled=True)
            },
            disabled=["id", "colaborador_email"], hide_index=True, num_rows="dynamic"
        )
        if st.button("💾 Salvar Alterações Tabela"):
            for i, row in edited_df.iterrows():
                if row["status_aprovaca"] != "Pendente" and not row["data_decisao"]:
                    edited_df.at[i, "data_decisao"] = datetime.now().strftime("%Y-%m-%d")
            conn.update(worksheet="lancamentos", data=edited_df.astype(str))
            st.success("Tabela atualizada!"); st.rerun()

    # ABA 3: BI
    with abas[2]:
        st.subheader("📊 Inteligência Financeira")
        df_bi = df_lancamentos.copy()
        df_bi["horas"] = pd.to_numeric(df_bi["horas"], errors="coerce").fillna(0)
        c_f, c_k = st.columns([1, 3])
        with c_f:
            ms = sorted([x for x in df_bi["competencia"].unique() if x], reverse=True)
            sel_m = st.selectbox("Competência", ["TODOS"] + (ms if ms else [datetime.now().strftime("%Y-%m")]))
        
        view = df_bi if sel_m == "TODOS" else df_bi[df_bi["competencia"] == sel_m]
        apr = view[view["status_aprovaca"] == "Aprovado"]
        tot_h = apr["horas"].sum()
        
        with c_k:
            k1, k2, k3 = st.columns(3)
            k1.metric("Horas", f"{tot_h:.1f}h"); k2.metric("Total R$", f"R$ {tot_h * valor_hora_padrao:,.2f}"); k3.metric("Registros", len(apr))
        st.divider()
        c1, c2 = st.columns(2)
        with c1:
            if not apr.empty:
                g = apr.groupby("colaborador_email").agg(Horas=("horas", "sum")).reset_index()
                g["R$"] = g["Horas"] * valor_hora_padrao
                st.dataframe(g, hide_index=True, use_container_width=True)
        with c2:
            if not apr.empty: st.bar_chart(apr.groupby("tipo")["horas"].sum())

    # ABA 4: CONFIGURAÇÕES (DESACOPLADA E SEGURA)
    with abas[3]:
        st.subheader("⚙️ Configurações do Sistema")
        st.info("💡 As listas abaixo são independentes. Edite e clique em Salvar.")
        
        c_proj, c_email, c_val = st.columns(3)
        with c_proj:
            st.markdown("##### 📂 Projetos")
            # Usa os dados carregados do sheet para preencher o editor
            df_p = pd.DataFrame({"projetos": lista_projetos})
            edit_p = st.data_editor(df_p, num_rows="dynamic", key="editor_projetos", hide_index=True, use_container_width=True)
            
        with c_email:
            st.markdown("##### 📧 Emails")
            df_e = pd.DataFrame({"emails_autorizados": lista_emails})
            edit_e = st.data_editor(df_e, num_rows="dynamic", key="editor_emails", hide_index=True, use_container_width=True)
            
        with c_val:
            st.markdown("##### 💰 Valor Hora")
            novo_val = st.number_input("R$", value=valor_hora_padrao, step=10.0)

        # DEBUG: Ver o que vai ser salvo
        with st.expander("🕵️‍♂️ Ver dados antes de Salvar (Debug)"):
            st.write("Projetos detectados:", edit_p["projetos"].tolist())
            st.write("Emails detectados:", edit_e["emails_autorizados"].tolist())

        if st.button("💾 Salvar Configurações"):
            # 1. Extração Limpa (Remove vazios e Nones)
            p_clean = [str(x).strip() for x in edit_p["projetos"].tolist() if str(x).strip() not in ["", "nan", "None"]]
            e_clean = [str(x).strip() for x in edit_e["emails_autorizados"].tolist() if str(x).strip() not in ["", "nan", "None"]]
            
            # 2. Garante que não está zerado (Backup de segurança)
            if not p_clean: p_clean = ["Sistema de horas"] # Nunca deixa zerar projetos
            
            # 3. Criação do Quadrado Perfeito
            max_len = max(len(p_clean), len(e_clean), 1)
            
            p_final = p_clean + [""] * (max_len - len(p_clean))
            e_final = e_clean + [""] * (max_len - len(e_clean))
            v_final = [novo_val] + [""] * (max_len - 1)
            
            df_save = pd.DataFrame({
                "projetos": p_final,
                "emails_autorizados": e_final,
                "valor_hora": v_final
            })
            
            # 4. Gravação
            conn.update(worksheet="config", data=df_save.astype(str))
            
            # 5. Limpeza de Cache Obrigatória
            st.cache_data.clear()
            st.cache_resource.clear()
            
            st.success("✅ Configurações salvas! A página irá recarregar.")
            time.sleep(2)
            st.rerun()