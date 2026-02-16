import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import uuid
import time

st.set_page_config(page_title="Oncall Management - v6", layout="wide", page_icon="🚀")

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
    df_lancamentos = pd.DataFrame(columns=["id", "data_registro", "competencia", "colaborador_email", "projeto", "tipo", "horas", "descricao", "status_aprovaca", "data_decisao"])

# Tratamentos Gerais
if "competencia" not in df_lancamentos.columns: df_lancamentos["competencia"] = ""
if "tipo" not in df_lancamentos.columns: df_lancamentos["tipo"] = "Geral"

mask_vazia = df_lancamentos["competencia"].isna() | (df_lancamentos["competencia"] == "") | (df_lancamentos["competencia"] == "nan")
if mask_vazia.any():
    datas_temp = pd.to_datetime(df_lancamentos.loc[mask_vazia, "data_registro"], errors='coerce')
    df_lancamentos.loc[mask_vazia, "competencia"] = datas_temp.dt.strftime("%Y-%m")
    df_lancamentos["competencia"] = df_lancamentos["competencia"].fillna(datetime.now().strftime("%Y-%m"))

df_lancamentos["status_aprovaca"] = df_lancamentos["status_aprovaca"].fillna("Pendente").replace("", "Pendente")
df_lancamentos["tipo"] = df_lancamentos["tipo"].fillna("Geral").replace("nan", "Geral")

# --- 3. LEITURA DE CONFIGURAÇÕES (COM TIPAGEM SEGURA) ---
try:
    # 1. Projetos (Lista de Strings)
    raw_proj = df_config["projetos"].unique().tolist()
    lista_projetos = [str(x).strip() for x in raw_proj if x and str(x).lower() not in ["nan", "none", "", "0"]]
    if not lista_projetos: lista_projetos = ["Sistema de horas"]

    # 2. Dicionário de Preços (Mapeamento Seguro)
    # Garante que valor seja float ou 0.0
    df_users = df_config[["emails_autorizados", "valor_hora"]].copy()
    df_users["valor_hora"] = pd.to_numeric(df_users["valor_hora"], errors="coerce").fillna(0.0)
    
    dict_valores = {}
    lista_emails = []
    
    for _, row in df_users.iterrows():
        email_val = str(row["emails_autorizados"]).strip()
        if "@" in email_val and email_val.lower() not in ["nan", "none", ""]:
            lista_emails.append(email_val)
            dict_valores[email_val] = float(row["valor_hora"])

except Exception as e:
    st.error(f"Erro ao ler configs: {e}")
    st.stop()

# --- 4. LOGIN ---
try:
    user_email = st.user.email
    if user_email is None: raise Exception()
except:
    user_email = "pedroivofernandesreis@gmail.com"

ADMINS = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]

if user_email not in ADMINS and user_email not in lista_emails:
    st.error(f"🔒 Acesso negado para {user_email}.")
    st.stop()

# --- 5. INTERFACE ---
st.title("Oncall Management - v6 (by Pedro Reis)")

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
        data_user = c3.date_input("Data da Atividade", value=datetime.now())
        
        c4, c5 = st.columns([1, 2])
        hor = c4.number_input("Horas", min_value=0.5, step=0.5, format="%.1f")
        desc = c5.text_area("Descrição")
        
        if st.form_submit_button("Enviar Registro"):
            comp_calc = data_user.strftime("%Y-%m")
            data_completa = data_user.strftime("%Y-%m-%d") + " " + datetime.now().strftime("%H:%M:%S")
            
            novo = pd.DataFrame([{
                "id": str(uuid.uuid4()),
                "data_registro": data_completa,
                "competencia": comp_calc,
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
            st.success(f"✅ Salvo para {data_user.strftime('%d/%m/%Y')}!")
            st.rerun()

# === ÁREA ADMIN ===
if user_email in ADMINS:
    
    # ABA 2: PAINEL DA CLAU
    with abas[1]:
        st.subheader("🛡️ Central de Controle")
        with st.expander("📥 Importar Excel"):
            arquivo = st.file_uploader("Arquivo .xlsx", type=["xlsx"])
            if arquivo and st.button("Processar"):
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
        if st.button("💾 Salvar Tabela"):
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
        df_bi["valor_hora_aplicado"] = df_bi["colaborador_email"].map(dict_valores).fillna(0)
        df_bi["custo_total"] = df_bi["horas"] * df_bi["valor_hora_aplicado"]
        
        c_f, c_k = st.columns([1, 3])
        with c_f:
            ms = sorted([x for x in df_bi["competencia"].unique() if x], reverse=True)
            sel_m = st.selectbox("Competência", ["TODOS"] + (ms if ms else [datetime.now().strftime("%Y-%m")]))
        
        view = df_bi if sel_m == "TODOS" else df_bi[df_bi["competencia"] == sel_m]
        apr = view[view["status_aprovaca"] == "Aprovado"]
        
        tot_h = apr["horas"].sum()
        tot_c = apr["custo_total"].sum()
        
        with c_k:
            k1, k2, k3 = st.columns(3)
            k1.metric("Horas", f"{tot_h:.1f}h"); k2.metric("Total", f"R$ {tot_c:,.2f}"); k3.metric("Registros", len(apr))
        st.divider()
        c1, c2 = st.columns(2)
        with c1:
            if not apr.empty:
                st.markdown("### 🏗️ Custo por Projeto")
                st.bar_chart(apr.groupby("projeto")["custo_total"].sum(), color="#00FF00")
        with c2:
            if not apr.empty:
                st.markdown("### 🛠️ Horas por Tipo")
                st.bar_chart(apr.groupby("tipo")["horas"].sum())
        
        st.markdown("### 👥 Pagamentos")
        if not apr.empty:
            g = apr.groupby("colaborador_email").agg(Horas=("horas", "sum"), Receber=("custo_total", "sum")).reset_index()
            g["Valor/h (Atual)"] = g["colaborador_email"].map(dict_valores).fillna(0)
            st.dataframe(g, column_config={"Receber": st.column_config.NumberColumn(format="R$ %.2f"), "Valor/h (Atual)": st.column_config.NumberColumn(format="R$ %.2f")}, hide_index=True, use_container_width=True)

    # ABA 4: CONFIGURAÇÕES (CORRIGIDA - SEM TRAVAMENTO)
    with abas[3]:
        st.subheader("⚙️ Configurações do Sistema")
        st.info("💡 As listas são independentes. **Projetos** são livres. **Colaboradores** precisam de valor hora.")
        
        col_proj, col_users = st.columns([1, 2])
        
        with col_proj:
            st.markdown("##### 📂 Projetos")
            df_p = pd.DataFrame({"projetos": lista_projetos})
            edit_p = st.data_editor(df_p, num_rows="dynamic", key="edit_p", hide_index=True, use_container_width=True)
            
        with col_users:
            st.markdown("##### 👥 Colaboradores & Valores")
            # PREPARAÇÃO DOS DADOS PARA O EDITOR (O SEGREDO DO SUCESSO)
            # 1. Pega dados brutos
            raw_e = df_config["emails_autorizados"].tolist()
            raw_v = df_config["valor_hora"].tolist()
            
            # 2. Normaliza Tamanhos
            max_len = max(len(raw_e), len(raw_v))
            raw_e += [""] * (max_len - len(raw_e))
            raw_v += [0.0] * (max_len - len(raw_v)) # PAD COM ZERO (FLOAT), NÃO STRING!
            
            # 3. Cria DataFrame Tipado
            df_u = pd.DataFrame({"emails_autorizados": raw_e, "valor_hora": raw_v})
            
            # 4. Força conversão para garantir que Streamlit receba números
            df_u["valor_hora"] = pd.to_numeric(df_u["valor_hora"], errors='coerce').fillna(0.0)
            
            edit_u = st.data_editor(
                df_u, 
                num_rows="dynamic", 
                key="edit_u", 
                hide_index=True, 
                use_container_width=True,
                column_config={
                    "valor_hora": st.column_config.NumberColumn("Valor Hora (R$)", step=0.5, format="%.2f")
                }
            )

        if st.button("💾 Salvar Configurações"):
            # 1. Limpeza Projetos
            p_clean = [str(x).strip() for x in edit_p["projetos"].tolist() if str(x).strip() not in ["", "nan", "None"]]
            if not p_clean: p_clean = ["Sistema de horas"]
            
            # 2. Limpeza Usuários (Pega par Email + Valor)
            e_clean = []
            v_clean = []
            for _, row in edit_u.iterrows():
                e_val = str(row["emails_autorizados"]).strip()
                v_val = row["valor_hora"] # Já é float
                
                if e_val and e_val not in ["", "nan", "None"]:
                    e_clean.append(e_val)
                    v_clean.append(v_val if v_val > 0 else 0.0)
            
            # 3. Montagem do Quadrado Perfeito
            max_len = max(len(p_clean), len(e_clean), 1)
            
            p_final = p_clean + [""] * (max_len - len(p_clean)) # Pad String
            e_final = e_clean + [""] * (max_len - len(e_clean)) # Pad String
            v_final = v_clean + [""] * (max_len - len(v_clean)) # Pad String (Convertemos pra string na hora de salvar)
            
            df_save = pd.DataFrame({
                "projetos": p_final,
                "emails_autorizados": e_final,
                "valor_hora": v_final
            })
            
            conn.update(worksheet="config", data=df_save.astype(str))
            
            st.cache_data.clear()
            st.cache_resource.clear()
            st.success("✅ Salvo com sucesso!")
            time.sleep(2)
            st.rerun()