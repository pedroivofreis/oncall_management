import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import uuid
import time
import io

# Configuração da Página
st.set_page_config(page_title="Oncall Management - v8.5", layout="wide", page_icon="🚀")

# --- 1. CONEXÃO ---
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 2. CARREGAMENTO ---
try:
    df_config = conn.read(worksheet="config", ttl=0)
    df_lancamentos = conn.read(worksheet="lancamentos", ttl=0)
    df_lancamentos.columns = [c.strip().lower() for c in df_lancamentos.columns]
except Exception as e:
    st.error("Erro ao carregar dados. Verifique as abas da planilha.")
    st.stop()

# --- 3. CONFIGURAÇÕES INDEPENDENTES ---
# Projetos e Usuários agora são lidos separadamente
lista_projetos = df_config["projetos"].dropna().astype(str).str.strip().unique().tolist()

df_u = df_config[["emails_autorizados", "valor_hora", "senhas"]].dropna(subset=["emails_autorizados"])
dict_users = {}
for _, row in df_u.iterrows():
    dict_users[row["emails_autorizados"].strip()] = {
        "valor": pd.to_numeric(row["valor_hora"], errors='coerce') or 0,
        "senha": str(row["senhas"]).strip()
    }

ADMINS = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]

# --- 4. LOGIN ---
st.sidebar.title("🔐 Acesso OnCall")
user_email = st.sidebar.selectbox("Usuário:", options=["Selecione..."] + sorted(list(dict_users.keys())))
autenticado = False

if user_email != "Selecione...":
    senha_digitada = st.sidebar.text_input("Senha:", type="password")
    if senha_digitada == dict_users[user_email]["senha"]:
        autenticado = True
    elif senha_digitada:
        st.sidebar.error("Senha incorreta.")

if not autenticado:
    st.info("👈 Identifique-se na lateral para acessar.")
    st.stop()

# --- 5. INTERFACE ---
tabs_list = ["📝 Lançar Horas", "📊 Meu Dashboard"]
if user_email in ADMINS:
    tabs_list += ["🛡️ Gerencial", "📈 BI Financeiro", "⚙️ Configurações"]
tabs = st.tabs(tabs_list)

# === ABA: LANÇAR HORAS (MULTILINHAS & EM MASSA) ===
with tabs[0]:
    metodo = st.radio("Forma de Lançamento:", ["Lançamento Dinâmico (+)", "Importação em Massa (Arquivo)"], horizontal=True)
    
    if metodo == "Lançamento Dinâmico (+)":
        st.markdown("### Adicione suas atividades abaixo:")
        # Criamos um DataFrame vazio para o editor
        df_template = pd.DataFrame(columns=["projeto", "tipo", "data", "horas", "descricão"])
        df_editor = st.data_editor(
            df_template, 
            num_rows="dynamic", 
            use_container_width=True,
            column_config={
                "projeto": st.column_config.SelectboxColumn("Projeto", options=lista_projetos, required=True),
                "tipo": st.column_config.SelectboxColumn("Tipo", options=["Front-end", "Back-end", "Banco de Dados", "Infra", "Testes", "Reunião", "Outros"], required=True),
                "data": st.column_config.DateColumn("Data", default=datetime.now(), required=True),
                "horas": st.column_config.NumberColumn("Horas", min_value=0.5, step=0.5, required=True),
                "descricão": st.column_config.TextColumn("Descrição", required=True)
            }
        )
        
        if st.button("🚀 Enviar Todos os Lançamentos"):
            if not df_editor.empty:
                novos_registros = []
                for _, r in df_editor.iterrows():
                    novos_registros.append({
                        "id": str(uuid.uuid4()), 
                        "data_registro": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "colaborador_email": user_email, 
                        "projeto": r["projeto"], 
                        "horas": str(r["horas"]),
                        "status_aprovaca": "Pendente", 
                        "data_decisao": "", 
                        "competencia": r["data"].strftime("%Y-%m") if hasattr(r["data"], 'strftime') else str(r["data"])[:7], 
                        "tipo": r["tipo"], 
                        "descricão": r["descricão"], 
                        "email_enviado": ""
                    })
                df_final = pd.concat([df_lancamentos, pd.DataFrame(novos_registros)], ignore_index=True)
                conn.update(worksheet="lancamentos", data=df_final.astype(str))
                st.success(f"✅ {len(novos_registros)} lançamentos enviados com sucesso!")
                time.sleep(1); st.rerun()
            else:
                st.warning("Adicione pelo menos uma linha no sinal de (+) à direita da tabela.")

    else:
        st.subheader("Importação por Arquivo")
        # Botão para baixar modelo
        modelo_csv = "projeto,horas,tipo,descricão,data\nProjeto Exemplo,2.5,Front-end,Desenvolvimento de tela,2024-02-15"
        st.download_button("📥 Baixar Modelo CSV", data=modelo_csv, file_name="modelo_oncall.csv", mime="text/csv")
        
        arquivo = st.file_uploader("Subir arquivo preenchido", type=["csv", "xlsx"])
        if arquivo:
            try:
                df_massa = pd.read_csv(arquivo) if arquivo.name.endswith('.csv') else pd.read_excel(arquivo)
                if st.button("Confirmar Importação em Massa"):
                    novos_massa = []
                    for _, r in df_massa.iterrows():
                        novos_massa.append({
                            "id": str(uuid.uuid4()), "data_registro": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "colaborador_email": user_email, "projeto": r["projeto"], "horas": str(r["horas"]),
                            "status_aprovaca": "Pendente", "data_decisao": "", 
                            "competencia": str(r["data"])[:7], "tipo": r["tipo"], "descricão": r["descricão"], "email_enviado": ""
                        })
                    df_final = pd.concat([df_lancamentos, pd.DataFrame(novos_massa)], ignore_index=True)
                    conn.update(worksheet="lancamentos", data=df_final.astype(str))
                    st.success(f"✅ {len(novos_massa)} registros importados!"); time.sleep(1); st.rerun()
            except Exception as e:
                st.error(f"Erro no arquivo: Verifique se as colunas estão iguais ao modelo.")

# === ABA: MEU DASHBOARD ===
with tabs[1]:
    meus_dados = df_lancamentos[df_lancamentos["colaborador_email"] == user_email].copy()
    meus_dados["horas"] = pd.to_numeric(meus_dados["horas"], errors="coerce").fillna(0)
    
    # Indicadores individuais
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Aprovadas", f"{meus_dados[meus_dados['status_aprovaca'] == 'Aprovado']['horas'].sum():.1f}h")
    c2.metric("Pagas", f"{meus_dados[meus_dados['status_aprovaca'] == 'Pago']['horas'].sum():.1f}h")
    c3.metric("Pendentes", f"{meus_dados[meus_dados['status_aprovaca'] == 'Pendente']['horas'].sum():.1f}h")
    c4.metric("Rejeitadas", f"{meus_dados[meus_dados['status_aprovaca'] == 'Rejeitado']['horas'].sum():.1f}h")
    
    st.divider()
    st.subheader("Histórico de Lançamentos")
    st.dataframe(meus_dados.sort_values("data_registro", ascending=False), use_container_width=True, hide_index=True)

# === ÁREA ADMIN ===
if user_email in ADMINS:
    with tabs[2]: # GERENCIAL
        sub1, sub2 = st.tabs(["✓ Aprovações", "💰 Pagamentos (Financeiro)"])
        with sub1:
            df_edit = st.data_editor(df_lancamentos, hide_index=True, use_container_width=True)
            if st.button("💾 Salvar Alterações Gerenciais"):
                conn.update(worksheet="lancamentos", data=df_edit.astype(str))
                st.success("Planilha atualizada!"); st.rerun()
        with sub2:
            mes = st.selectbox("Competência:", sorted(df_lancamentos["competencia"].unique(), reverse=True))
            df_p = df_lancamentos[(df_lancamentos["competencia"] == mes) & (df_lancamentos["status_aprovaca"] == "Aprovado")].copy()
            df_p["horas"] = pd.to_numeric(df_p["horas"], errors="coerce").fillna(0)
            df_p["total"] = df_p["colaborador_email"].map(lambda x: dict_users.get(x, {}).get("valor", 0)) * df_p["horas"]
            
            resumo = df_p.groupby("colaborador_email")["total"].sum().reset_index()
            st.dataframe(resumo.style.format({"total": "R$ {:.2f}"}), use_container_width=True)
            
            if st.button(f"Confirmar Pagamento Total de {mes}"):
                df_lancamentos.loc[(df_lancamentos["competencia"] == mes) & (df_lancamentos["status_aprovaca"] == "Aprovado"), "status_aprovaca"] = "Pago"
                conn.update(worksheet="lancamentos", data=df_lancamentos.astype(str))
                st.success("Status atualizado para PAGO!"); st.rerun()

    with tabs[3]: # BI
        filt = st.multiselect("Filtrar Meses:", sorted(df_lancamentos["competencia"].unique()), default=sorted(df_lancamentos["competencia"].unique()))
        df_bi = df_lancamentos[df_lancamentos["competencia"].isin(filt)].copy()
        df_bi["horas"] = pd.to_numeric(df_bi["horas"], errors="coerce").fillna(0)
        df_bi["custo"] = df_bi["horas"] * df_bi["colaborador_email"].map(lambda x: dict_users.get(x, {}).get("valor", 0))
        
        validos = df_bi[df_bi["status_aprovaca"].isin(["Aprovado", "Pago"])]
        st.metric("Custo Total Selecionado", f"R$ {validos['custo'].sum():,.2f}")
        st.bar_chart(validos.groupby("projeto")["custo"].sum())

    with tabs[4]: # CONFIG
        st.info("Aqui você pode gerenciar Projetos e Usuários de forma independente.")
        conf_edit = st.data_editor(df_config, num_rows="dynamic", hide_index=True, use_container_width=True)
        if st.button("💾 Salvar Configurações Globais"):
            conn.update(worksheet="config", data=conf_edit.astype(str))
            st.success("Configurações aplicadas!"); st.rerun()

# --- RODAPÉ ---
st.markdown("---")
st.markdown(f"<p style='text-align: center; color: grey;'>Projeto by <b>Pedro Reis</b> | OnCall Management v8.5</p>", unsafe_allow_html=True)