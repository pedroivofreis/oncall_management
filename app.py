import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import uuid
import time
import io
from sqlalchemy import text

# ==============================================================================
# 1. CONFIGURAÇÃO DA PÁGINA E ESTILIZAÇÃO (UI ENTERPRISE)
# ==============================================================================
st.set_page_config(
    page_title="OnCall Humana - Master v8.2", 
    layout="wide", 
    page_icon="🛡️",
    initial_sidebar_state="expanded"
)

# CSS Customizado para garantir leitura em Dark/Light Mode e espaçamentos corretos
st.markdown("""
<style>
    /* Espaçamento do container principal */
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 5rem;
    }
    
    /* Cards de Métricas (KPIs) com borda sutil */
    div[data-testid="stMetric"] {
        background-color: rgba(255, 255, 255, 0.03); /* Transparencia sutil */
        border: 1px solid rgba(128, 128, 128, 0.2);
        padding: 15px;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    
    /* Labels de formulários mais fortes */
    label {
        font-weight: 600 !important;
        font-size: 0.9rem !important;
    }
    
    /* Cabeçalhos de Expander mais visíveis */
    .streamlit-expanderHeader {
        font-weight: 700;
        font-size: 1.0rem;
        color: #0068c9; /* Azul Streamlit */
    }
    
    /* Tabelas com bordas definidas */
    div[data-testid="stDataFrame"] {
        border: 1px solid rgba(128, 128, 128, 0.15);
        border-radius: 5px;
    }
    
    /* Botões Primários */
    button[kind="primary"] {
        font-weight: bold;
        border: 1px solid rgba(255, 75, 75, 0.5);
    }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 2. GERENCIAMENTO DE CONEXÃO COM O BANCO DE DADOS
# ==============================================================================
def get_connection():
    """
    Estabelece uma conexão segura com o banco de dados Neon (PostgreSQL).
    Inclui uma query de 'wake-up' para garantir que bancos serverless 
    estejam ativos antes de tentar operações pesadas.
    """
    try:
        # Cria a conexão usando a engine nativa do Streamlit
        c = st.connection("postgresql", type="sql")
        
        # Query leve para testar a latência e acordar o banco
        c.query("SELECT 1", ttl=0) 
        
        return c
    except Exception as e:
        # Tratamento de erro fatal
        st.error("🔴 Erro Crítico de Conexão com o Banco de Dados.")
        st.error(f"Detalhe do erro: {e}")
        st.info("Verifique se as credenciais no arquivo `.streamlit/secrets.toml` estão corretas.")
        st.stop() # Para a execução do app

conn = get_connection()

# ==============================================================================
# 3. LÓGICA DE NEGÓCIO E FUNÇÕES UTILITÁRIAS
# ==============================================================================

def convert_to_decimal_hours(pseudo_hour):
    """
    Converte o formato visual HH.MM (Ex: 2.30 = 2h 30min) para Decimal (2.50).
    Essencial para o cálculo financeiro: Valor = Horas Decimais * Valor Hora.
    
    Exemplos:
    - Input: 1.30 (1 hora e 30 min) -> Output: 1.50
    - Input: 1.45 (1 hora e 45 min) -> Output: 1.75
    """
    try:
        if pd.isna(pseudo_hour): 
            return 0.0
        
        # Garante formatação string com 2 casas decimais para separar H e M
        val_str = f"{float(pseudo_hour):.2f}"
        parts = val_str.split('.')
        
        horas_inteiras = int(parts[0])
        minutos = int(parts[1])
        
        # Proteção: Se minutos >= 60, assume que o usuário já digitou decimal puro
        if minutos >= 60:
            return float(pseudo_hour)
            
        # Conversão matemática real: Minutos / 60
        horas_decimais = horas_inteiras + (minutos / 60)
        
        return horas_decimais
    except Exception:
        # Em caso de erro de conversão, retorna 0 para não quebrar o cálculo
        return 0.0

def normalize_text_for_bi(text_val):
    """
    Padroniza nomes de Tipos e Projetos para limpeza do BI e Gráficos.
    Remove inconsistências como 'Backend', 'Back-end', 'back end'.
    """
    if not isinstance(text_val, str): 
        return "Outros"
        
    t = text_val.strip().lower()
    
    # Regras de normalização
    if "back" in t and "end" in t: return "Back-end"
    if "front" in t and "end" in t: return "Front-end"
    if "dados" in t or "data" in t: return "Eng. Dados"
    if "infra" in t or "devops" in t: return "Infraestrutura"
    if "qa" in t or "test" in t or "qualidade" in t: return "QA / Testes"
    if "banco" in t and "dados" in t: return "Banco de Dados"
    if "reuni" in t or "meeting" in t: return "Reunião"
    if "gest" in t or "agile" in t: return "Gestão"
    if "design" in t or "ux" in t or "ui" in t: return "Design/UX"
    
    return text_val.capitalize()

# ==============================================================================
# 4. CARREGAMENTO DE DADOS (READ-ONLY)
# ==============================================================================
# Usamos ttl=0 para garantir dados sempre frescos (sem cache)

def get_all_data(): 
    """Busca tabela completa de lançamentos."""
    return conn.query("SELECT * FROM lancamentos ORDER BY competencia DESC, data_registro DESC", ttl=0)

def get_config_users(): 
    """Busca tabela de usuários."""
    return conn.query("SELECT * FROM usuarios ORDER BY email", ttl=0)

def get_config_projs(): 
    """Busca tabela de projetos."""
    return conn.query("SELECT * FROM projetos ORDER BY nome", ttl=0)

def get_bancos(): 
    """Busca dados bancários."""
    return conn.query("SELECT * FROM dados_bancarios", ttl=0)

# ==============================================================================
# 5. SISTEMA DE AUTENTICAÇÃO E MAPEAMENTO DE NOMES
# ==============================================================================
# Carrega dados brutos dos usuários
df_u_login = get_config_users()

# --- MAPEAMENTO DE NOMES (CRUCIAL PARA UI) ---
# Cria um dicionário {email: Nome Real} para substituir visualmente em todo o sistema
email_to_name = {}
for row in df_u_login.itertuples():
    # Verifica se a coluna 'nome' existe e tem dados
    if hasattr(row, 'nome') and row.nome and str(row.nome).strip() != "":
        email_to_name[row.email] = row.nome
    else:
        # Fallback: Cria um nome baseado no email (ex: pedro.reis -> Pedro Reis)
        fallback_name = row.email.split('@')[0].replace('.', ' ').title()
        email_to_name[row.email] = fallback_name

# --- DICIONÁRIO MESTRE DE AUTH ---
# Estrutura central para validar senha e permissões
dict_users = {row.email: {
    "valor": float(row.valor_hora) if row.valor_hora else 0.0, 
    "senha": str(row.senha), 
    "is_admin": bool(getattr(row, 'is_admin', False)),
    "nome_real": email_to_name.get(row.email)
} for row in df_u_login.itertuples()}

# Lista de Super Admins (Fallback de segurança)
SUPER_ADMINS = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]

# --- SIDEBAR DE LOGIN ---
st.sidebar.title("🛡️ OnCall Humana")
st.sidebar.caption("v8.2 Titanium Monolith")

# Lógica do Selectbox: Mostra "Nome (Email)" mas retorna o índice para buscarmos o email
lista_emails = list(dict_users.keys())
# Cria lista visual formatada
opcoes_visual = [f"{email_to_name.get(e, e)} ({e})" for e in lista_emails]
# Cria mapa reverso: "Nome (Email)" -> "email@dominio.com"
login_map = dict(zip(opcoes_visual, lista_emails))

user_selection = st.sidebar.selectbox("👤 Identifique-se:", ["..."] + options=opcoes_visual)

if user_selection == "...":
    st.info("👈 Selecione seu usuário no menu lateral para acessar o sistema.")
    st.image("https://img.freepik.com/free-vector/access-control-system-abstract-concept_335657-3180.jpg", use_container_width=True)
    st.stop()

# Recupera o email real baseado na escolha visual
user_email = login_map[user_selection] 
user_name_display = dict_users[user_email]["nome_real"]

senha_input = st.sidebar.text_input("🔑 Senha de Acesso:", type="password")

if senha_input != dict_users[user_email]["senha"]:
    st.sidebar.warning("Aguardando senha correta...")
    st.stop()

# Definição de Permissão Master
is_user_admin = dict_users[user_email]["is_admin"] or user_email in SUPER_ADMINS

# Feedback Visual de Login
if is_user_admin:
    st.sidebar.success(f"Logado como ADMIN: {user_name_display}")
else:
    st.sidebar.info(f"Bem-vindo, {user_name_display}")

# ==============================================================================
# 6. MENU DE NAVEGAÇÃO PERSISTENTE
# ==============================================================================
st.sidebar.divider()
st.sidebar.subheader("📍 Menu Principal")

# Opções de Menu baseadas no Perfil
if is_user_admin:
    menu_options = [
        "📝 Lançamentos", 
        "📊 Meu Painel / Gestão", 
        "🛡️ Admin Aprovações", 
        "💸 Pagamentos", 
        "📈 BI Estratégico", 
        "⚙️ Configurações"
    ]
else:
    menu_options = [
        "📝 Lançamentos", 
        "📊 Meu Painel"
    ]

# O radio button mantém o estado da sessão, evitando o refresh indesejado
escolha = st.sidebar.radio("Ir para:", menu_options)

# ==============================================================================
# 7. CARREGAMENTO E PROCESSAMENTO GLOBAL DE DADOS (DATA E NOME)
# ==============================================================================
df_lan = get_all_data()
df_projs = get_config_projs()
df_banc = get_bancos()

# Tratamento de listas para Selectbox
lista_projetos = df_projs['nome'].tolist() if not df_projs.empty else ["Sustentação", "Projetos", "Outros"]

# Listas para filtros (Exclusivas para Admin)
colaboradores_emails = sorted(df_lan['colaborador_email'].unique()) if not df_lan.empty else []
# Cria lista visual de colaboradores (Nome + Email)
colaboradores_visual = [f"{email_to_name.get(e, e)} ({e})" for e in colaboradores_emails]

# --- TRATAMENTO CRÍTICO DE DADOS ---
# O sistema precisa diferenciar Data de Registro (Log) de Data da Atividade (Competência)
if not df_lan.empty:
    # 1. Injeta o NOME do colaborador no DataFrame principal para facilitar visualização
    df_lan['Nome'] = df_lan['colaborador_email'].map(email_to_name).fillna(df_lan['colaborador_email'])
    
    # 2. Tratamento de Data Real da Atividade
    # Tenta ler a coluna 'data_atividade' (nova). Se não existir ou for nula, usa 'competencia'
    if 'data_atividade' in df_lan.columns:
        df_lan['Data Real'] = pd.to_datetime(df_lan['data_atividade'], errors='coerce').dt.date
    else:
        # Se a coluna não existir no DF, cria vazia
        df_lan['Data Real'] = pd.NaT

    # 3. Tratamento de Data de Importação (Log do Sistema)
    df_lan['Importado Em'] = pd.to_datetime(df_lan['data_registro']).dt.date
    
    # 4. Fallback Final: Se Data Real for nula, usa a Data de Importação para não quebrar filtro
    df_lan['Data Real'] = df_lan['Data Real'].fillna(df_lan['Importado Em'])

# ==============================================================================
# ABA 1: LANÇAMENTOS (INDIVIDUAL)
# ==============================================================================
if escolha == "📝 Lançamentos":
    st.subheader(f"📝 Registro de Atividade - {user_name_display}")
    
    with st.expander("ℹ️ Guia de Preenchimento (Leia antes)", expanded=False):
        st.markdown("""
        1. **Projeto:** Escolha onde você alocou suas horas.
        2. **Data Real:** Informe o dia exato que você trabalhou (pode ser retroativo).
        3. **Horas:** Use o formato **HH.MM** (Ex: `1.30` para 1h30min, `0.45` para 45min).
        4. **Descrição:** Seja detalhado para facilitar a aprovação.
        """)
    
    with st.form("form_lancamento_main", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        
        proj_sel = c1.selectbox("Projeto", lista_projetos)
        tipo_sel = c2.selectbox("Tipo de Atividade", ["Front-end", "Back-end", "Infra", "QA", "Dados", "Reunião", "Gestão", "Design", "Apoio", "Outros"])
        
        # CAMPO CRÍTICO: DATA DA ATIVIDADE
        # O usuário seleciona a data real que trabalhou
        d_real = c3.date_input("Data REAL da Atividade", datetime.now())
        
        c4, c5 = st.columns([1, 2])
        # Input formatado para HH.MM
        horas_input = c4.number_input("Horas Trabalhadas (HH.MM)", min_value=0.0, step=0.10, format="%.2f")
        desc_input = c5.text_input("Descrição detalhada (O que foi entregue?)")
        
        btn_gravar = st.form_submit_button("🚀 Gravar Lançamento")
        
        if btn_gravar:
            # Validações Lógicas
            if horas_input <= 0:
                st.warning("⚠️ As horas devem ser maiores que zero.")
            elif not desc_input:
                st.warning("⚠️ A descrição é obrigatória.")
            else:
                try:
                    # PREPARAÇÃO DOS DADOS PARA O INSERT
                    # 1. Competência (YYYY-MM) para filtros macro
                    competencia_str = d_real.strftime("%Y-%m")
                    # 2. Data Completa (YYYY-MM-DD) para filtros exatos e auditoria
                    data_full_str = d_real.strftime("%Y-%m-%d")
                    
                    with conn.session as s:
                        # SQL EXPLÍCITO COM TODAS AS COLUNAS
                        s.execute(
                            text("""
                                INSERT INTO lancamentos 
                                (id, colaborador_email, projeto, horas, competencia, data_atividade, tipo, descricao, valor_hora_historico) 
                                VALUES (:id, :e, :p, :h, :c, :d_atv, :t, :d, :v)
                            """),
                            {
                                "id": str(uuid.uuid4()), 
                                "e": user_email, 
                                "p": proj_sel, 
                                "h": horas_input, 
                                "c": competencia_str,   # COMPETENCIA
                                "d_atv": data_full_str, # DATA ATIVIDADE
                                "t": tipo_sel, 
                                "d": desc_input, 
                                "v": dict_users[user_email]["valor"]
                            }
                        )
                        s.commit()
                    st.success(f"✅ Atividade de {horas_input}h salva para o dia {d_real.strftime('%d/%m/%Y')} com sucesso!")
                    time.sleep(1); st.rerun()
                except Exception as e:
                    st.error("Erro ao salvar no banco de dados.")
                    st.code(str(e)) # Exibe o erro técnico para debug

# ==============================================================================
# ABA 2: MEU PAINEL / GESTÃO (FILTRO POR COMPETÊNCIA + NOME)
# ==============================================================================
elif "Meu Painel" in escolha:
    st.subheader("📊 Painel de Controle Financeiro")
    
    # --- SELETOR DE USUÁRIO ALVO (VISÃO ADMIN) ---
    target_email = user_email
    target_name_curr = user_name_display
    
    if is_user_admin:
        col_sel_admin, _ = st.columns([2, 2])
        # Selectbox com "Nome (Email)"
        # Filtra a lista para remover o próprio usuário da lista de "Outros" para evitar duplicação visual
        lista_outros = [x for x in colaboradores_visual if user_email not in x]
        lista_adm = [f"{user_name_display} ({user_email})"] + lista_outros
        
        sel_admin = col_sel_admin.selectbox(
            "👁️ (Admin) Visualizar Painel de:", 
            lista_adm
        )
        # Extrai email do string selecionado
        target_email = sel_admin.split('(')[-1].replace(')', '')
        target_name_curr = email_to_name.get(target_email, target_email)
    
    st.info(f"Visualizando dados de: **{target_name_curr}**")
    
    # --- FILTRO POR COMPETÊNCIA (MULTI-SELECT) ---
    st.write("---")
    
    # Pega todas as competências únicas do banco para montar o filtro
    if not df_lan.empty:
        # Pega a coluna competencia, converte para string, pega unicos, ordena reverso
        all_comps = sorted(df_lan['competencia'].astype(str).unique(), reverse=True)
    else:
        all_comps = []
        
    c_f1, c_f2 = st.columns([1, 3])
    
    # Multi-Select corrige o problema de filtrar datas quebradas
    # Permite selecionar múltiplos meses (ex: Janeiro e Fevereiro)
    comp_selecionadas = c_f1.multiselect(
        "📅 Filtrar Competência(s):", 
        all_comps, 
        default=all_comps[:1] if all_comps else None
    )
    
    # --- FILTRAGEM DO DATAFRAME ---
    # 1. Filtra pelo usuário alvo
    df_m = df_lan[df_lan["colaborador_email"] == target_email].copy()
    
    # 2. Filtra pela competência selecionada
    if not df_m.empty and comp_selecionadas:
        df_m = df_m[df_m['competencia'].isin(comp_selecionadas)]
    
    if not df_m.empty and comp_selecionadas:
        # 3. Cálculos Financeiros (Real-time)
        df_m['h_dec'] = df_m['horas'].apply(convert_to_decimal_hours)
        df_m['r$'] = df_m['h_dec'] * df_m['valor_hora_historico']
        
        # --- SCORECARDS DE AUDITORIA ---
        st.markdown("### Resumo Financeiro")
        k1, k2, k3, k4 = st.columns(4)
        
        h_pend = df_m[df_m['status_aprovaca'] == 'Pendente']['horas'].sum()
        h_aprov = df_m[df_m['status_aprovaca'] == 'Aprovado']['horas'].sum()
        h_pago = df_m[df_m['status_pagamento'] == 'Pago']['horas'].sum()
        val_total = df_m['r$'].sum()
        
        k1.metric("Pendente (HH.MM)", f"{h_pend:.2f}")
        k2.metric("Aprovado (HH.MM)", f"{h_aprov:.2f}")
        k3.metric("Pago (HH.MM)", f"{h_pago:.2f}")
        k4.metric("Valor Total (R$)", f"R$ {val_total:,.2f}")
        
        st.divider()
        st.markdown(f"### 📋 Extrato Detalhado - {target_name_curr}")
        
        # Seleção de Colunas para Exibição
        # Note que usamos 'Data Real' (que vem de data_atividade)
        df_view = df_m[['descricao', 'Data Real', 'projeto', 'horas', 'r$', 'status_aprovaca', 'status_pagamento']]
        
        st.dataframe(
            df_view, 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "r$": st.column_config.NumberColumn("Valor (R$)", format="R$ %.2f"),
                "horas": st.column_config.NumberColumn("Horas (HH.MM)", format="%.2f"),
                "Data Real": st.column_config.DateColumn("Data Atividade", format="DD/MM/YYYY"),
                "status_aprovaca": st.column_config.TextColumn("Status Aprovação"),
                "status_pagamento": st.column_config.TextColumn("Pagamento"),
                "descricao": st.column_config.TextColumn("Descrição", width="large"),
                "projeto": st.column_config.TextColumn("Projeto")
            }
        )
    else:
        if not comp_selecionadas:
            st.warning("👆 Selecione pelo menos uma competência (Mês/Ano) acima para ver os dados.")
        else:
            st.info("Nenhum registro encontrado para as competências selecionadas.")

# ==============================================================================
# ABA 3: ADMIN APROVAÇÕES (BIPARTIDA + BULK IMPORT)
# ==============================================================================
elif escolha == "🛡️ Admin Aprovações":
    st.subheader("🛡️ Central de Gestão Operacional")
    
    # --- BLOCO A: IMPORTAÇÃO EM MASSA ---
    with st.expander("📥 Importação em Massa (Copiar e Colar do Excel)", expanded=False):
        st.info("Cole os dados. O sistema identificará o e-mail, calculará o valor e salvará a data real.")
        st.markdown("""
        **Formato Obrigatório (Separado por TAB):**
        `Data (DD/MM/AAAA)` | `Projeto` | `Email` | `Horas (HH.MM)` | `Tipo` | `Descrição`
        """)
        
        cola_texto = st.text_area("Área de Transferência:", height=150)
        
        if cola_texto and st.button("🚀 Processar Importação em Massa"):
            try:
                # Leitura flexível (assume separador TAB que vem do Excel)
                df_p = pd.read_csv(io.StringIO(cola_texto), sep='\t', names=["data", "p", "e", "h", "t", "d"])
                
                with conn.session as s:
                    for r in df_p.itertuples():
                        # Busca valor hora do usuário (ou 0 se não achar)
                        v_h = dict_users.get(r.e, {}).get("valor", 0)
                        
                        # TRATAMENTO DATA DUPLO (DD/MM/AAAA -> YYYY-MM-DD)
                        try:
                            dt_obj = pd.to_datetime(r.data, dayfirst=True)
                            comp_str = dt_obj.strftime("%Y-%m")      # Para Filtros
                            data_full = dt_obj.strftime("%Y-%m-%d")  # Para Auditoria
                        except:
                            # Fallback para hoje se a data estiver em formato ruim
                            now = datetime.now()
                            comp_str = now.strftime("%Y-%m")
                            data_full = now.strftime("%Y-%m-%d")

                        s.execute(
                            text("""
                                INSERT INTO lancamentos 
                                (id, colaborador_email, projeto, horas, competencia, data_atividade, tipo, descricao, valor_hora_historico) 
                                VALUES (:id, :e, :p, :h, :c, :d_atv, :t, :d, :v)
                            """),
                            {
                                "id": str(uuid.uuid4()), "e": r.e, "p": r.p, "h": r.h, 
                                "c": comp_str, "d_atv": data_full, 
                                "t": r.t, "d": r.d, "v": v_h
                            }
                        )
                    s.commit()
                st.success(f"{len(df_p)} registros importados com sucesso!"); time.sleep(1); st.rerun()
            except Exception as e: 
                st.error("Erro na leitura dos dados. Verifique se copiou as colunas na ordem correta.")
                st.code(str(e))

    st.divider()

    # --- BLOCO B: PENDENTES ---
    st.markdown("### 🕒 Fila de Pendentes")
    
    # Controles de Tabela
    c_all, c_fil = st.columns([1, 3])
    sel_all = c_all.checkbox("Selecionar Todos")
    
    # Filtro por NOME (Lista Visual)
    lista_filtro_nomes = ["Todos"] + colaboradores_visual
    f_p_nome = c_fil.selectbox("Filtrar por Nome:", lista_filtro_nomes, key="fp_admin")
    
    df_p = df_lan[df_lan['status_aprovaca'] == 'Pendente'].copy()
    
    # Aplica filtro (revertendo visual -> email)
    if f_p_nome != "Todos":
        email_sel = f_p_nome.split('(')[-1].replace(')', '') # Extrai email
        df_p = df_p[df_p['colaborador_email'] == email_sel]
    
    # Monta Tabela visualmente rica (NOME + PROJETO + DATA REAL)
    if not df_p.empty:
        # Seleciona colunas
        df_p = df_p[['descricao', 'Nome', 'projeto', 'Data Real', 'horas', 'id']]
        
        # Insere checkboxes de controle
        # Se 'Selecionar Todos' estiver marcado, a coluna começa True
        df_p.insert(0, "✅", sel_all) 
        df_p.insert(1, "🗑️", False)
        
        ed_p = st.data_editor(
            df_p, 
            use_container_width=True, 
            hide_index=True, 
            key="ed_pend",
            column_config={
                "✅": st.column_config.CheckboxColumn("Aprovar", width="small"),
                "🗑️": st.column_config.CheckboxColumn("Excluir", width="small"),
                "Data Real": st.column_config.DateColumn("Data Ativ.", format="DD/MM/YYYY"),
                "horas": st.column_config.NumberColumn("HH.MM", format="%.2f"),
                "Nome": st.column_config.TextColumn("Colaborador", width="medium"),
                "descricao": st.column_config.TextColumn("Descrição", width="large")
            }
        )
        
        c1, c2 = st.columns(2)
        if c1.button("✔️ APROVAR SELECIONADOS", type="primary"):
            ids_aprov = ed_p[ed_p["✅"] == True]["id"].tolist()
            if ids_aprov:
                with conn.session as s:
                    s.execute(text("UPDATE lancamentos SET status_aprovaca = 'Aprovado' WHERE id IN :ids"), {"ids": tuple(ids_aprov)})
                    s.commit()
                st.success(f"{len(ids_aprov)} itens aprovados!"); time.sleep(0.5); st.rerun()
                
        if c2.button("🔥 NEGAR SELECIONADOS"):
            ids_neg = ed_p[ed_p["🗑️"] == True]["id"].tolist()
            if ids_neg:
                with conn.session as s:
                    # Move para Negado (Rejeitados)
                    s.execute(text("UPDATE lancamentos SET status_aprovaca = 'Negado' WHERE id IN :ids"), {"ids": tuple(ids_neg)})
                    s.commit()
                st.warning(f"{len(ids_neg)} itens movidos para rejeitados."); time.sleep(0.5); st.rerun()
    else:
        st.info("Nenhuma pendência encontrada.")

    st.divider()

    # --- BLOCO C: APROVADOS (EDIÇÃO) ---
    st.markdown("### ✅ Histórico de Aprovados")
    st.caption("Edite aqui itens já aprovados caso precise corrigir.")
    
    f_a_nome = st.selectbox("Filtrar Aprovados:", lista_filtro_nomes, key="fa_admin")
    
    df_a = df_lan[df_lan['status_aprovaca'] == 'Aprovado'].copy()
    if f_a_nome != "Todos":
        email_sel_a = f_a_nome.split('(')[-1].replace(')', '')
        df_a = df_a[df_a['colaborador_email'] == email_sel_a]
    
    if not df_a.empty:
        # Exibe Nome e Data Real para edição
        df_a = df_a[['descricao', 'Nome', 'projeto', 'Data Real', 'horas', 'status_aprovaca', 'id']]
        
        ed_a = st.data_editor(
            df_a, use_container_width=True, hide_index=True, key="ed_aprov",
            column_config={
                "status_aprovaca": st.column_config.SelectboxColumn("Status", options=["Aprovado", "Pendente", "Negado"], required=True),
                "Data Real": st.column_config.DateColumn("Data Ativ.", format="DD/MM/YYYY"),
                "horas": st.column_config.NumberColumn("HH.MM", format="%.2f"),
                "Nome": st.column_config.TextColumn("Colaborador", disabled=True)
            }
        )
        if st.button("💾 Salvar Alterações em Aprovados"):
            with conn.session as s:
                for r in ed_a.itertuples():
                    s.execute(text("UPDATE lancamentos SET status_aprovaca = :s, horas = :h, descricao = :d WHERE id = :id"),
                              {"s": r.status_aprovaca, "h": r.horas, "d": r.descricao, "id": r.id})
                s.commit()
            st.success("Alterações salvas!"); time.sleep(0.5); st.rerun()
    else:
        st.info("Nenhum item aprovado para este filtro.")

    # --- BLOCO D: REJEITADOS ---
    st.divider()
    with st.expander("❌ Ver Rejeitados / Lixeira"):
        df_n = df_lan[df_lan['status_aprovaca'] == 'Negado'].copy()
        if not df_n.empty:
            df_n = df_n[['descricao', 'Nome', 'Data Real', 'status_aprovaca', 'id']]
            
            ed_n = st.data_editor(
                df_n, use_container_width=True, hide_index=True, 
                column_config={
                    "status_aprovaca": st.column_config.SelectboxColumn("Ação", options=["Negado", "Pendente", "Aprovado"]),
                    "Data Real": st.column_config.DateColumn("Data")
                }
            )
            
            c_rec, c_del = st.columns(2)
            if c_rec.button("💾 Recuperar/Salvar Rejeitados"):
                with conn.session as s:
                    for r in ed_n.itertuples():
                        if r.status_aprovaca != "Negado":
                            s.execute(text("UPDATE lancamentos SET status_aprovaca = :s WHERE id = :id"), {"s": r.status_aprovaca, "id": r.id})
                    s.commit()
                st.success("Itens recuperados!"); st.rerun()
                
            if c_del.button("🔥 EXCLUIR DEFINITIVAMENTE", type="primary"):
                with conn.session as s:
                    ids_del = tuple(ed_n[ed_n['status_aprovaca'] == 'Negado']['id'].tolist())
                    if ids_del:
                        s.execute(text("DELETE FROM lancamentos WHERE id IN :ids"), {"ids": ids_del})
                        s.commit()
                st.warning("Itens excluídos permanentemente."); st.rerun()
        else:
            st.info("Lixeira vazia.")

# ==============================================================================
# ABA 4: PAGAMENTOS (DRILL-DOWN COM NOMES E COMPETÊNCIA)
# ==============================================================================
elif escolha == "💸 Pagamentos":
    st.subheader("💸 Consolidação Financeira")
    
    df_pay = df_lan[df_lan['status_aprovaca'] == 'Aprovado'].copy()
    if not df_pay.empty:
        # Conversão Financeira
        df_pay['h_dec'] = df_pay['horas'].apply(convert_to_decimal_hours)
        df_pay['r$'] = df_pay['h_dec'] * df_pay['valor_hora_historico']
        
        # Agrupa por COMPETENCIA (YYYY-MM) e Colaborador
        df_g = df_pay.groupby(['competencia', 'colaborador_email']).agg({'r$': 'sum', 'horas': 'sum'}).reset_index()
        
        # Totalizador Geral
        total_open = df_pay[df_pay['status_pagamento'] != 'Pago']['r$'].sum()
        st.metric("Total Pendente Geral (Todos)", f"R$ {total_open:,.2f}")
        
        # Ordena grupos pela competência mais recente
        df_g = df_g.sort_values(['competencia', 'colaborador_email'], ascending=[False, True])
        
        for idx, row in df_g.iterrows():
            # Recupera nome bonito para o Expander
            nome_c = email_to_name.get(row['colaborador_email'], row['colaborador_email'])
            
            with st.expander(f"📅 {row['competencia']} | 👤 {nome_c} | Total: R$ {row['r$']:,.2f}"):
                
                det = df_pay[(df_pay['competencia'] == row['competencia']) & (df_pay['colaborador_email'] == row['colaborador_email'])]
                
                st.dataframe(
                    det[['descricao', 'Data Real', 'horas', 'r$']], 
                    use_container_width=True, hide_index=True, 
                    column_config={
                        "r$": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
                        "Data Real": st.column_config.DateColumn("Data"),
                        "horas": st.column_config.NumberColumn("HH.MM", format="%.2f")
                    }
                )
                
                # Controle de Status do Grupo
                s_atu = det['status_pagamento'].iloc[0] if 'status_pagamento' in det.columns else "Em aberto"
                op = ["Em aberto", "Pago", "Parcial"]
                idx_op = op.index(s_atu) if s_atu in op else 0
                
                c_s, c_b = st.columns([3, 1])
                ns = c_s.selectbox("Status", op, index=idx_op, key=f"p_{idx}")
                
                if c_b.button("Atualizar Pagamento", key=f"b_{idx}"):
                    with conn.session as s:
                        ids_u = tuple(det['id'].tolist())
                        s.execute(text("UPDATE lancamentos SET status_pagamento=:s WHERE id IN :ids"), {"s": ns, "ids": ids_u})
                        s.commit()
                    st.success("Atualizado!"); time.sleep(0.5); st.rerun()
    else:
        st.info("Nenhum lançamento aprovado para gerar pagamento.")

# ==============================================================================
# ABA 5: BI ESTRATÉGICO (FILTRO COMPETENCIA + NOMES)
# ==============================================================================
elif escolha == "📈 BI Estratégico":
    st.subheader("📈 Inteligência de Negócios")
    
    # Filtro Multi-Select por COMPETENCIA
    all_comps_bi = sorted(df_lan['competencia'].astype(str).unique(), reverse=True) if not df_lan.empty else []
    
    c1, c2 = st.columns([3, 1])
    comp_bi = c1.multiselect("Filtrar Período (Competência):", all_comps_bi, default=all_comps_bi[:2])
    
    df_bi = df_lan.copy()
    
    if comp_bi and not df_bi.empty:
        # Filtra DF
        df_bi = df_bi[df_bi['competencia'].isin(comp_bi)]
        
        # Normalização e Cálculos
        df_bi['tipo_norm'] = df_bi['tipo'].apply(normalize_text_for_bi)
        df_bi['h_dec'] = df_bi['horas'].apply(convert_to_decimal_hours)
        df_bi["custo"] = df_bi['h_dec'] * df_bi["valor_hora_historico"]
        
        # Cards
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Horas Totais", f"{df_bi['horas'].sum():.2f}")
        m2.metric("Custo Total", f"R$ {df_bi['custo'].sum():,.2f}")
        m3.metric("Pago", f"R$ {df_bi[df_bi['status_pagamento']=='Pago']['custo'].sum():,.2f}")
        m4.metric("Registros", len(df_bi))
        
        # Gráficos
        c1, c2 = st.columns(2)
        with c1: 
            st.write("**💰 Custo por Projeto**")
            st.bar_chart(df_bi.groupby("projeto")["custo"].sum())
        with c2: 
            st.write("**⏱️ Horas por Tipo de Atividade**")
            st.bar_chart(df_bi.groupby("tipo_norm")["horas"].sum())
        
        st.divider()
        st.write("**🏆 Ranking de Colaboradores (Por Nome)**")
        # Agrupa pelo NOME (Coluna criada no inicio)
        rank = df_bi.groupby("Nome").agg({'horas': 'sum', 'custo': 'sum'}).sort_values('horas', ascending=False)
        st.dataframe(rank, use_container_width=True, column_config={"custo": st.column_config.NumberColumn("R$", format="%.2f")})
    else:
        st.info("Selecione uma competência para visualizar os gráficos.")

# ==============================================================================
# ABA 6: CONFIGURAÇÕES (COM COLUNA NOME)
# ==============================================================================
elif escolha == "⚙️ Configurações":
    st.subheader("⚙️ Configurações do Sistema")
    
    # --- USUÁRIOS ---
    st.write("👥 **Gestão de Usuários e Nomes**")
    st.caption("Edite o 'Nome de Exibição' para que os relatórios fiquem mais amigáveis.")
    
    ed_u = st.data_editor(
        df_u_login, 
        num_rows="dynamic", 
        hide_index=True, 
        column_config={
            "email": st.column_config.TextColumn("Login/Email", disabled=True),
            "nome": st.column_config.TextColumn("Nome de Exibição"),
            "senha": st.column_config.TextColumn("Senha"),
            "is_admin": st.column_config.CheckboxColumn("Admin"),
            "valor_hora": st.column_config.NumberColumn("Valor/Hora (R$)", format="R$ %.2f")
        }
    )
    if st.button("Salvar Usuários"):
        with conn.session as s:
            for r in ed_u.itertuples():
                nm = getattr(r, 'nome', r.email.split('@')[0])
                if pd.isna(nm) or str(nm).strip() == "":
                    nm = r.email.split('@')[0]
                
                # Upsert seguro
                s.execute(
                    text("""
                        INSERT INTO usuarios (email, valor_hora, senha, is_admin, nome) 
                        VALUES (:e, :v, :s, :a, :n) 
                        ON CONFLICT (email) 
                        DO UPDATE SET valor_hora=:v, senha=:s, is_admin=:a, nome=:n
                    """), 
                    {"e": r.email, "v": r.valor_hora, "s": str(r.senha), "a": bool(r.is_admin), "n": nm}
                )
            s.commit()
        st.success("Usuários atualizados!"); time.sleep(0.5); st.rerun()
        
    st.divider()
    
    # --- PROJETOS ---
    st.write("📁 **Projetos**")
    ed_p = st.data_editor(df_projs, num_rows="dynamic", hide_index=True)
    if st.button("Salvar Projetos"):
        with conn.session as s:
            for r in ed_p.itertuples():
                if r.nome: 
                    s.execute(text("INSERT INTO projetos (nome) VALUES (:n) ON CONFLICT (nome) DO NOTHING"), {"n": r.nome})
            s.commit()
        st.success("Projetos salvos!"); st.rerun()

    st.divider()
    
    # --- BANCOS ---
    st.write("🏦 **Dados Bancários**")
    ed_b = st.data_editor(
        df_banc, 
        num_rows="dynamic", 
        hide_index=True, 
        column_config={
            "tipo_chave": st.column_config.SelectboxColumn("Tipo", options=["CPF", "CNPJ", "Email", "Aleatoria", "Conta"])
        }
    )
    if st.button("Salvar Bancos"):
        with conn.session as s:
            for r in ed_b.itertuples():
                t_key = getattr(r, 'tipo_chave', 'CPF')
                s.execute(
                    text("""
                        INSERT INTO dados_bancarios (colaborador_email, banco, tipo_chave, chave_pix) 
                        VALUES (:e, :b, :t, :c) 
                        ON CONFLICT (colaborador_email) 
                        DO UPDATE SET banco=:b, tipo_chave=:t, chave_pix=:c
                    """), 
                    {"e": r.colaborador_email, "b": r.banco, "t": t_key, "c": r.chave_pix}
                )
            s.commit()
        st.success("Dados bancários salvos!"); st.rerun()

# ==============================================================================
# RODAPÉ
# ==============================================================================
st.markdown("---")
st.markdown(
    "<p style='text-align: center; color: gray; font-size: 12px;'>"
    "OnCall Humana - Developed by Pedro Reis | v8.2 Titanium Monolith | "
    f"Status: Online | {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    "</p>", 
    unsafe_allow_html=True
)