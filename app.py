import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import uuid

# Configuração visual do sistema
st.set_page_config(page_title="Gestão de Horas - OnCall", layout="wide")

# Identificação do Usuário
try:
    user_email = st.user.email
except:
    # E-mail de fallback caso o Streamlit não capture o login
    user_email = "pedroivofernandesreis@gmail.com"

# Lista de Administradores com acesso total
ADMINS = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]

# Inicializa a conexão com o Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

# --- CARREGAMENTO SEGURO DE DADOS ---
# Tentativa de leitura da aba de CONFIGURAÇÕES
try:
    df_config = conn.read(worksheet="config")
except Exception:
    # Se a aba estiver vazia ou com erro, cria estrutura padrão
    df_config = pd.DataFrame(columns=["projetos", "emails_autorizados", "valor_hora"])

# Tentativa de leitura da aba de LANÇAMENTOS
try:
    df_lancamentos_atual = conn.read(worksheet="lancamentos")
except Exception:
    # Estrutura base para evitar erro de leitura em abas vazias
    df_lancamentos_atual = pd.DataFrame(columns=[
        "id", "data_registro", "colaborador_email", "projeto", 
        "horas", "descricao", "status_aprovaca", "data_decisao"
    ])

# Extração de listas para os filtros e validação
lista_projetos = df_config["projetos"].dropna().unique().tolist()
if not lista_projetos:
    lista_projetos = ["Sistema de horas"] # Nome definido por você

lista_autorizados = df_config["emails_autorizados"].dropna().unique().tolist()

# --- FILTRO DE SEGURANÇA ---
if user_email not in ADMINS and user_email not in lista_autorizados:
    st.error(f"Acesso negado para {user_email}. Solicite autorização à gestora.")
    st.stop()

# Definição das Abas de Navegação
if user_email in ADMINS:
    abas = st.tabs(["🚀 Lançar Horas", "🛡️ Painel da Clau", "📊 Dashboard BI", "⚙️ Configurações"])
else:
    abas = st.tabs(["🚀 Lançar Horas"])

# --- ABA 1: LANÇAMENTO DE HORAS ---
with abas[0]:
    st.header("Novo Lançamento")
    with st.form("form_horas", clear_on_submit=True):
        col1, col2 = st.columns(2)
        projeto_sel = col1.selectbox("Selecione o Projeto", lista_projetos)
        horas_val = col2.number_input("Horas Trabalhadas", min_value=0.5, step=0.5)
        desc_val = st.text_area("O que você desenvolveu?")
        
        if st.form_submit_button("Enviar para Aprovação"):
            novo_registro = pd.DataFrame([{
                "id": str(uuid.uuid4()),
                "data_registro": datetime.now().strftime("%d/%m/%Y %H:%M"),
                "colaborador_email": user_email,
                "projeto": projeto_sel,
                "horas": horas_val,
                "descricao": desc_val,
                "status_aprovaca": "Pendente",
                "data_decisao": ""
            }])
            
            # Atualiza a planilha concatenando o novo dado
            df_final = pd.concat([df_lancamentos_atual, novo_registro], ignore_index=True)
            conn.update(worksheet="lancamentos", data=df_final)
            st.success("Lançamento registrado com sucesso! ✅")

# --- CONTEÚDO EXCLUSIVO PARA ADMINISTRADORES ---
if user_email in ADMINS:
    # --- ABA 2: PAINEL DE GESTÃO (APROVAÇÕES) ---
    with abas[1]:
        st.header("Aprovações Pendentes")
        pendentes = df_lancamentos_atual[df_lancamentos_atual['status_aprovaca'] == 'Pendente']
        
        if not pendentes.empty:
            df_editado = st.data_editor(pendentes, use_container_width=True, key="editor_gestao")
            if st.button("Confirmar Aprovações"):
                df_lancamentos_atual.update(df_editado)
                conn.update(worksheet="lancamentos", data=df_lancamentos_atual)
                st.success("Status atualizados!")
                st.rerun()
        else:
            st.info("Nenhum lançamento aguardando aprovação.")

    # --- ABA 3: DASHBOARD BI ---
    with abas[2]:
        st.header("Visão Financeira")
        df_aprovado = df_lancamentos_atual[df_lancamentos_atual['status_aprovaca'] == 'Aprovado'].copy()
        
        # Merge com a config para calcular o custo baseado no valor_hora do colaborador
        df_custo = df_aprovado.merge(
            df_config[['emails_autorizados', 'valor_hora']], 
            left_on='colaborador_email', 
            right_on='emails_autorizados', 
            how='left'
        )
        
        df_custo['total_r$'] = df_custo['horas'] * df_custo['valor_hora'].fillna(0)

        m1, m2 = st.columns(2)
        m1.metric("Horas Aprovadas", f"{df_custo['horas'].sum()}h")
        m2.metric("Investimento Total", f"R$ {df_custo['total_r$'].sum():,.2f}")
        
        st.subheader("Custo por Projeto")
        st.bar_chart(df_custo.groupby("projeto")["total_r$"].sum())

    # --- ABA 4: CONFIGURAÇÕES (GERENCIAMENTO) ---
    with abas[3]:
        st.header("Painel Administrativo")
        st.write("Cadastre projetos globais e autorize colaboradores com seus respectivos valores/hora.")
        
        df_config_edit = st.data_editor(df_config, num_rows="dynamic", use_container_width=True)
        
        if st.button("Salvar Novas Configurações"):
            conn.update(worksheet="config", data=df_config_edit)
            st.success("Configurações salvas! Reiniciando...")
            st.rerun()