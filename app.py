import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import uuid
import time
import io
from sqlalchemy import text

# ==============================================================================
# 1. CONFIGURAÇÃO DA PÁGINA E ESTILIZAÇÃO VISUAL
# ==============================================================================
st.set_page_config(
    page_title="OnCall Humana - Master v6.6 Colossus", 
    layout="wide", 
    page_icon="🛡️",
    initial_sidebar_state="expanded"
)

# CSS Customizado para melhorar a leitura dos Scorecards e Tabelas
st.markdown("""
<style>
    /* Melhoria visual dos Metrics */
    div[data-testid="stMetric"] {
        background-color: #f8f9fa;
        border: 1px solid #e9ecef;
        padding: 10px;
        border-radius: 5px;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.05);
    }
    /* Destaque para headers de Expander */
    .streamlit-expanderHeader {
        font-weight: bold;
        color: #0f54c9;
    }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 2. CONEXÃO COM O BANCO DE DADOS (NEON POSTGRES)
# ==============================================================================
def get_connection():
    """
    Estabelece a conexão com o banco de dados Neon.
    Inclui tratamento de erro robusto e 'wake-up call' para serverless.
    """
    try:
        c = st.connection("postgresql", type="sql")
        # Query leve para garantir que a conexão está ativa e o banco "acordado"
        c.query("SELECT 1", ttl=0) 
        return c
    except Exception as e:
        st.error(f"🔴 Erro Crítico de Conexão com o Banco de Dados: {e}")
        st.stop()

conn = get_connection()

# ==============================================================================
# 3. LÓGICA DE NEGÓCIO E UTILITÁRIOS MATEMÁTICOS
# ==============================================================================

def convert_to_decimal_hours(pseudo_hour):
    """
    Converte o formato visual HH.MM (usado pelos humanos) para decimal (usado pelo financeiro).
    
    Lógica:
    - O usuário digita 2.30 (significando 2 horas e 30 minutos).
    - Matematicamente, 2.30 horas é diferente de 2h 30min (que seria 2.5 horas).
    - Esta função corrige essa distorção.
    
    Exemplos:
    - Input: 2.30 -> Output: 2.50
    - Input: 1.50 -> Output: 1.8333...
    """
    try:
        if pd.isna(pseudo_hour): return 0.0
        
        # Garante duas casas decimais como string para separar corretamente
        val_str = f"{float(pseudo_hour):.2f}"
        parts = val_str.split('.')
        
        horas_inteiras = int(parts[0])
        minutos = int(parts[1])
        
        # Proteção: Se o usuário digitar 2.90 (90 minutos), tratamos como decimal puro
        if minutos >= 60:
            return float(pseudo_hour)
            
        horas_decimais = horas_inteiras + (minutos / 60)
        return horas_decimais
    except Exception:
        return 0.0

def normalize_text_for_bi(text_val):
    """
    Normaliza nomes de Tipos e Projetos para evitar duplicidade nos gráficos.
    Resolve problemas como: 'Backend ', 'Back-end', 'backend' -> 'Back-end'
    """
    if not isinstance(text_val, str): return text_val
    
    t = text_val.strip().lower()
    
    # Regras de normalização
    if "back" in t and "end" in t: return "Back-end"
    if "front" in t and "end" in t: return "Front-end"
    if "data" in t or "dados" in t: return "Eng. Dados"
    if "banco" in t: return "Banco de Dados"
    if "qa" in t or "quality" in t: return "QA / Testes"
    
    return text_val.capitalize()

# ==============================================================================
# 4. FUNÇÕES DE CARREGAMENTO DE DADOS (SEM CACHE - REAL TIME)
# ==============================================================================
def get_all_data(): 
    """Busca todos os lançamentos ordenados por data."""
    return conn.query("SELECT * FROM lancamentos ORDER BY data_registro DESC", ttl=0)

def get_config_users(): 
    """Busca tabela de usuários, senhas e permissões."""
    return conn.query("SELECT * FROM usuarios", ttl=0)

def get_config_projs(): 
    """Busca tabela de projetos cadastrados."""
    return conn.query("SELECT * FROM projetos", ttl=0)

def get_bancos(): 
    """Busca dados bancários dos colaboradores."""
    return conn.query("SELECT * FROM dados_bancarios", ttl=0)

# ==============================================================================
# 5. SISTEMA DE LOGIN E PERMISSÕES
# ==============================================================================
df_u_login = get_config_users()

# Cria dicionário de autenticação para acesso rápido
dict_users = {row.email: {
    "valor": float(row.valor_hora), 
    "senha": str(row.senha), 
    "is_admin": bool(getattr(row, 'is_admin', False)) 
} for row in df_u_login.itertuples()}

# Lista de Super Admins (Fallback de segurança caso o banco falhe)
SUPER_ADMINS = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]

# --- SIDEBAR DE LOGIN ---
st.sidebar.title("🛡️ OnCall Humana")
st.sidebar.caption("v6.6 Colossus Edition")

# Seletor de Usuário
user_email = st.sidebar.selectbox("👤 Identifique-se:", ["..."] + list(dict_users.keys()))

if user_email == "...":
    st.info("👈 Selecione seu usuário no menu lateral para acessar o sistema.")
    st.image("https://img.freepik.com/free-vector/access-control-system-abstract-concept_335657-3180.jpg", use_container_width=True)
    st.stop()

# Input de Senha
senha_input = st.sidebar.text_input("🔑 Senha de Acesso:", type="password")

# Validação de Senha
if senha_input != dict_users[user_email]["senha"]:
    st.sidebar.warning("Senha incorreta. Acesso negado.")
    st.stop()

# Define Variável de Permissão Master
is_user_admin = dict_users[user_email]["is_admin"] or user_email in SUPER_ADMINS

if is_user_admin:
    st.sidebar.success(f"Logado como ADMIN: {user_email.split('@')[0]}")
else:
    st.sidebar.info(f"Logado como: {user_email.split('@')[0]}")

# ==============================================================================
# 6. MENU DE NAVEGAÇÃO PERSISTENTE
# ==============================================================================
st.sidebar.divider()
st.sidebar.subheader("📍 Navegação")

# Opções de Menu baseadas no Perfil
if is_user_admin:
    menu_options = [
        "📝 Lançamentos", 
        "📊 Meu Painel / Gestão",  # Nome alterado para refletir o poder do Admin
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

# O radio button mantém o estado da sessão, evitando o refresh para a aba 1
escolha = st.sidebar.radio("Ir para:", menu_options)

# ==============================================================================
# 7. CARREGAMENTO GLOBAL DE VARIÁVEIS E TRATAMENTO
# ==============================================================================
df_lan = get_all_data()
df_projs = get_config_projs()
df_banc = get_bancos()

# Tratamento de listas para Selectbox
lista_projetos = df_projs['nome'].tolist() if not df_projs.empty else ["Sustentação", "Projetos", "Outros"]
colaboradores = sorted(df_lan['colaborador_email'].unique()) if not df_lan.empty else []

# TRATAMENTO DE DATAS (CRUCIAL PARA OS FILTROS FUNCIONAREM CORRETAMENTE)
# Assumimos que a coluna 'competencia' guarda a data da atividade (YYYY-MM-DD)
# e 'data_registro' guarda o log do sistema.
if not df_lan.empty:
    df_lan['data_atividade'] = pd.to_datetime(df_lan['competencia'], errors='coerce').dt.date
    df_lan['data_importacao'] = pd.to_datetime(df_lan['data_registro']).dt.date
    # Fallback: Se competencia for nula, usa a data de importação
    df_lan['data_atividade'] = df_lan['data_atividade'].fillna(df_lan['data_importacao'])

# ==============================================================================
# ABA 1: LANÇAMENTOS (INDIVIDUAL)
# ==============================================================================
if escolha == "📝 Lançamentos":
    st.subheader("📝 Registro Individual de Atividade")
    st.markdown("""
    **Instruções de Preenchimento:**
    1. **Data:** Informe a data real em que a atividade foi realizada.
    2. **Horas:** Utilize o formato **HH.MM** (Exemplo: `1.30` para 1 hora e 30 minutos).
    3. **Descrição:** Detalhe o que foi entregue.
    """)
    
    with st.form("form_lancamento_individual", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        
        proj_sel = c1.selectbox("Projeto", lista_projetos)
        tipo_sel = c2.selectbox("Tipo de Atividade", ["Front-end", "Back-end", "Infra", "QA", "Dados", "Reunião", "Gestão", "Design"])
        # IMPORTANTE: A data inputada aqui vai para a coluna 'competencia'
        data_sel = c3.date_input("Data Real da Atividade", datetime.now())
        
        c4, c5 = st.columns([1, 2])
        # Input formatado para HH.MM
        horas_input = c4.number_input("Horas Trabalhadas (HH.MM)", min_value=0.0, step=0.10, format="%.2f")
        desc_input = c5.text_input("Descrição detalhada da entrega (O que foi feito?)")
        
        btn_gravar = st.form_submit_button("🚀 Gravar Lançamento no Banco")
        
        if btn_gravar:
            # Validações Básicas
            if horas_input <= 0:
                st.error("⚠️ As horas devem ser maiores que zero.")
            elif not desc_input:
                st.error("⚠️ A descrição é obrigatória.")
            else:
                try:
                    with conn.session as s:
                        s.execute(
                            text("""
                                INSERT INTO lancamentos 
                                (id, colaborador_email, projeto, horas, competencia, tipo, descricao, valor_hora_historico) 
                                VALUES (:id, :e, :p, :h, :c, :t, :d, :v)
                            """),
                            {
                                "id": str(uuid.uuid4()), 
                                "e": user_email, 
                                "p": proj_sel, 
                                "h": horas_input, 
                                # Salvando YYYY-MM-DD para permitir filtro de data exata
                                "c": data_sel.strftime("%Y-%m-%d"), 
                                "t": tipo_sel, 
                                "d": desc_input, 
                                "v": dict_users[user_email]["valor"]
                            }
                        )
                        s.commit()
                    st.success("✅ Lançamento gravado com sucesso!")
                    time.sleep(0.5)
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao gravar no banco: {e}")

# ==============================================================================
# ABA 2: MEU PAINEL (AGORA COM VISÃO DE TERCEIROS PARA ADMIN)
# ==============================================================================
elif "Meu Painel" in escolha:
    st.subheader("📊 Painel Financeiro e de Horas")
    
    # --- LÓGICA DE VISUALIZAÇÃO DE ADMIN ---
    target_user = user_email # Padrão: vê os próprios dados
    
    if is_user_admin:
        st.info("🔓 **Modo Admin Ativo**: Você tem permissão para visualizar o painel de outros colaboradores.")
        col_sel_user, col_spacer = st.columns([1, 3])
        # Selectbox para escolher qual usuário visualizar
        selected_view = col_sel_user.selectbox(
            "👁️ Visualizar dados de:", 
            [user_email] + [c for c in colaboradores if c != user_email]
        )
        target_user = selected_view
    
    st.markdown(f"**Exibindo dados de:** `{target_user}`")
    
    # --- FILTROS DE DATA (ATIVIDADE REAL) ---
    c_f1, c_f2 = st.columns(2)
    data_ini = c_f1.date_input("Início (Data Atividade):", datetime.now() - timedelta(days=30))
    data_fim = c_f2.date_input("Fim (Data Atividade):", datetime.now())
    
    # Filtragem dos dados
    df_m = df_lan[df_lan["colaborador_email"] == target_user].copy()
    
    if not df_m.empty:
        # Filtra pela coluna de atividade (competencia) e não pelo registro
        df_m = df_m[(df_m['data_atividade'] >= data_ini) & (df_m['data_atividade'] <= data_fim)]
    
    if not df_m.empty:
        # Cálculos Financeiros (Conversão HH.MM -> Decimal)
        df_m['h_dec'] = df_m['horas'].apply(convert_to_decimal_hours)
        df_m['total_r$'] = df_m['h_dec'] * df_m['valor_hora_historico']
        
        # --- SCORECARDS DE AUDITORIA ---
        st.markdown("### Resumo do Período")
        k1, k2, k3, k4 = st.columns(4)
        
        # Filtra horas por status
        hrs_pend = df_m[df_m['status_aprovaca'] == 'Pendente']['horas'].sum()
        hrs_aprov = df_m[df_m['status_aprovaca'] == 'Aprovado']['horas'].sum()
        hrs_pago = df_m[df_m['status_pagamento'] == 'Pago']['horas'].sum()
        val_total = df_m['total_r$'].sum()
        
        k1.metric("Pendente (HH.MM)", f"{hrs_pend:.2f}")
        k2.metric("Aprovado (HH.MM)", f"{hrs_aprov:.2f}")
        k3.metric("Pago (HH.MM)", f"{hrs_pago:.2f}")
        k4.metric("Valor Total Estimado", f"R$ {val_total:,.2f}")
        
        st.divider()
        st.markdown("### Detalhamento dos Lançamentos")
        
        # Organização de colunas (Descrição primeiro, ID oculto/ultimo)
        cols_view = ['descricao', 'data_atividade', 'data_importacao', 'projeto', 'horas', 'total_r$', 'status_aprovaca', 'status_pagamento']
        
        st.dataframe(
            df_m[cols_view], 
            use_container_width=True, 
            hide_index=True, 
            column_config={
                "total_r$": st.column_config.NumberColumn("Valor (R$)", format="R$ %.2f"),
                "horas": st.column_config.NumberColumn("Horas (HH.MM)", format="%.2f"),
                "data_atividade": st.column_config.DateColumn("Data Real"),
                "data_importacao": st.column_config.DateColumn("Importado em", format="DD/MM/YYYY"),
                "status_aprovaca": st.column_config.TextColumn("Status Aprovação"),
                "status_pagamento": st.column_config.TextColumn("Status Pagamento"),
                "descricao": "Atividade / Entrega",
                "projeto": "Projeto"
            }
        )
    else:
        st.warning(f"Nenhum lançamento encontrado para {target_user} no período selecionado.")

# ==============================================================================
# ABA 3: ADMIN APROVAÇÕES (GESTAO COMPLETA E BIPARTIDA)
# ==============================================================================
elif escolha == "🛡️ Admin Aprovações":
    st.subheader("🛡️ Central de Controle Admin")
    
    # --- BLOCO A: IMPORTAÇÃO EM MASSA (EXPANDER) ---
    with st.expander("📥 Importação em Massa (Copiar e Colar do Excel)"):
        st.info("Cole os dados do Excel. O sistema calculará o valor automaticamente com base no e-mail do usuário.")
        st.markdown("**Ordem das Colunas:** Data (DD/MM/AAAA) | Projeto | E-mail | Horas (HH.MM) | Tipo | Descrição")
        
        cola_texto = st.text_area("Área de Transferência:", height=150)
        
        if cola_texto:
            if st.button("🚀 Processar e Gravar em Massa"):
                try:
                    # Lê TSV (Tab Separated Values - padrão do Excel copy)
                    df_paste = pd.read_csv(io.StringIO(cola_texto), sep='\t', names=["data", "projeto", "usuario", "horas", "tipo", "descricao"])
                    
                    st.write("Prévia:")
                    st.dataframe(df_paste.head())
                    
                    with conn.session as s:
                        for r in df_paste.itertuples():
                            # Busca valor hora
                            v_h = dict_users.get(r.usuario, {}).get("valor", 0)
                            
                            # Converte data DD/MM/AAAA para YYYY-MM-DD
                            dt_obj = pd.to_datetime(r.data, dayfirst=True)
                            comp_gen = dt_obj.strftime("%Y-%m-%d")
                            
                            s.execute(
                                text("""
                                    INSERT INTO lancamentos 
                                    (id, colaborador_email, projeto, horas, competencia, tipo, descricao, valor_hora_historico) 
                                    VALUES (:id, :e, :p, :h, :c, :t, :d, :v)
                                """),
                                {
                                    "id": str(uuid.uuid4()), "e": r.usuario, "p": r.projeto, "h": r.horas, 
                                    "c": comp_gen, "t": r.tipo, "d": r.descricao, "v": v_h
                                }
                            )
                        s.commit()
                    st.success("Importação concluída!")
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro na importação: {e}")

    st.divider()

    # --- BLOCO B: TABELA DE PENDENTES ---
    st.markdown("### 🕒 Fila de Pendentes (Avaliação)")
    
    # Filtros e Seleção
    col_sel, col_fil = st.columns([1, 3])
    # Checkbox que controla a seleção de todos
    select_all_pend = col_sel.checkbox("Selecionar Todos (Pendentes)")
    
    filter_colab_pend = col_fil.selectbox("Filtrar por Colaborador:", ["Todos"] + colaboradores, key="fp_admin")
    
    # Query Base Pendentes
    df_p = df_lan[df_lan['status_aprovaca'] == 'Pendente'].copy()
    if filter_colab_pend != "Todos":
        df_p = df_p[df_p['colaborador_email'] == filter_colab_pend]
    
    # Monta Tabela Editável
    # DESCRIÇÃO PRIMEIRO, ID ÚLTIMO, PROJETO VISÍVEL
    df_p = df_p[['descricao', 'projeto', 'colaborador_email', 'data_atividade', 'data_importacao', 'horas', 'tipo', 'id']]
    
    # Insere colunas de controle
    # Se 'select_all_pend' for True, inicializa a coluna '✅' como True
    df_p.insert(0, "✅", select_all_pend) 
    df_p.insert(1, "🗑️", False)          
    
    ed_p = st.data_editor(
        df_p, 
        use_container_width=True, 
        hide_index=True, 
        key="editor_pendentes",
        column_config={
            "✅": st.column_config.CheckboxColumn("Aprovar", width="small"),
            "🗑️": st.column_config.CheckboxColumn("Excluir", width="small"),
            "horas": st.column_config.NumberColumn("HH.MM", format="%.2f"),
            "data_atividade": st.column_config.DateColumn("Data Real"),
            "data_importacao": st.column_config.DateColumn("Importado em")
        }
    )
    
    # Botões de Ação
    c_btn1, c_btn2 = st.columns(2)
    
    if c_btn1.button("✔️ APROVAR SELECIONADOS", use_container_width=True):
        ids_aprov = ed_p[ed_p["✅"] == True]["id"].tolist()
        if ids_aprov:
            with conn.session as s:
                s.execute(text("UPDATE lancamentos SET status_aprovaca = 'Aprovado' WHERE id IN :ids"), {"ids": tuple(ids_aprov)})
                s.commit()
            st.success(f"{len(ids_aprov)} itens aprovados!")
            time.sleep(0.5); st.rerun()
            
    if c_btn2.button("🔥 NEGAR/EXCLUIR SELECIONADOS", type="primary", use_container_width=True):
        ids_neg = ed_p[ed_p["🗑️"] == True]["id"].tolist()
        if ids_neg:
            with conn.session as s:
                # Mudando para 'Negado' para cair na tabela de rejeitados
                s.execute(text("UPDATE lancamentos SET status_aprovaca = 'Negado' WHERE id IN :ids"), {"ids": tuple(ids_neg)})
                s.commit()
            st.warning(f"{len(ids_neg)} itens movidos para Rejeitados!")
            time.sleep(0.5); st.rerun()

    st.divider()

    # --- BLOCO C: TABELA DE APROVADOS (EDIÇÃO) ---
    st.markdown("### ✅ Histórico de Aprovados (Edição)")
    st.caption("Use esta tabela para corrigir lançamentos já aprovados.")
    
    filter_colab_aprov = st.selectbox("Filtrar Aprovados:", ["Todos"] + colaboradores, key="fa_admin")
    
    df_a = df_lan[df_lan['status_aprovaca'] == 'Aprovado'].copy()
    if filter_colab_aprov != "Todos":
        df_a = df_a[df_a['colaborador_email'] == filter_colab_aprov]
        
    df_a = df_a[['descricao', 'projeto', 'colaborador_email', 'data_atividade', 'horas', 'status_aprovaca', 'id']]
    
    ed_a = st.data_editor(
        df_a, 
        use_container_width=True, 
        hide_index=True, 
        key="editor_aprovados",
        column_config={
            "status_aprovaca": st.column_config.SelectboxColumn("Status", options=["Aprovado", "Pendente", "Negado"], required=True),
            "horas": st.column_config.NumberColumn("HH.MM", format="%.2f")
        }
    )
    
    if st.button("💾 Salvar Edições em Aprovados"):
        with conn.session as s:
            for r in ed_a.itertuples():
                s.execute(
                    text("UPDATE lancamentos SET status_aprovaca = :s, horas = :h, descricao = :d, projeto = :p WHERE id = :id"),
                    {"s": r.status_aprovaca, "h": r.horas, "d": r.descricao, "p": r.projeto, "id": r.id}
                )
            s.commit()
        st.success("Alterações salvas!")
        time.sleep(0.5); st.rerun()

    st.divider()

    # --- BLOCO D: TABELA DE REJEITADOS ---
    with st.expander("❌ Ver Itens Rejeitados / Negados"):
        st.markdown("Itens aqui não são contabilizados no financeiro.")
        
        df_n = df_lan[df_lan['status_aprovaca'] == 'Negado'].copy()
        
        if not df_n.empty:
            df_n = df_n[['descricao', 'projeto', 'colaborador_email', 'horas', 'status_aprovaca', 'id']]
            
            ed_n = st.data_editor(
                df_n, 
                use_container_width=True, 
                hide_index=True, 
                key="editor_negados",
                column_config={
                    "status_aprovaca": st.column_config.SelectboxColumn("Ação", options=["Negado", "Pendente", "Aprovado"])
                }
            )
            
            col_n1, col_n2 = st.columns(2)
            if col_n1.button("💾 Recuperar Itens Rejeitados"):
                with conn.session as s:
                    for r in ed_n.itertuples():
                        if r.status_aprovaca != "Negado":
                            s.execute(text("UPDATE lancamentos SET status_aprovaca = :s WHERE id = :id"), {"s": r.status_aprovaca, "id": r.id})
                    s.commit()
                st.success("Itens recuperados!")
                st.rerun()
                
            if col_n2.button("🔥 EXCLUIR DEFINITIVAMENTE", type="primary"):
                ids_del = ed_n['id'].tolist()
                if ids_del:
                    with conn.session as s:
                        s.execute(text("DELETE FROM lancamentos WHERE id IN :ids"), {"ids": tuple(ids_del)})
                        s.commit()
                    st.warning("Itens excluídos permanentemente do banco.")
                    st.rerun()
        else:
            st.info("Nenhum item rejeitado.")

# ==============================================================================
# ABA 4: PAGAMENTOS (DRILL-DOWN COM CÁLCULO REAL)
# ==============================================================================
elif escolha == "💸 Pagamentos":
    st.subheader("💸 Consolidação de Pagamentos")
    
    df_pay = df_lan[df_lan['status_aprovaca'] == 'Aprovado'].copy()
    
    if not df_pay.empty:
        # Conversão Lógica
        df_pay['h_dec'] = df_pay['horas'].apply(convert_to_decimal_hours)
        df_pay['r$'] = df_pay['h_dec'] * df_pay['valor_hora_historico']
        
        # Agrupa pela Competência (Mês/Ano do banco ou da atividade)
        # Vamos criar uma chave de agrupamento baseada na Data da Atividade (YYYY-MM)
        df_pay['mes_ref'] = pd.to_datetime(df_pay['data_atividade']).dt.strftime('%Y-%m')
        
        # Agrupamento
        df_g = df_pay.groupby(['mes_ref', 'colaborador_email']).agg({'r$': 'sum', 'horas': 'sum'}).reset_index()
        
        total_pendente = df_pay[df_pay['status_pagamento'] != 'Pago']['r$'].sum()
        st.metric("Total Pendente de Pagamento (Geral)", f"R$ {total_pendente:,.2f}")
        
        # Drill-down
        for idx, row in df_g.iterrows():
            with st.expander(f"📅 {row['mes_ref']} | 👤 {row['colaborador_email']} | Total: R$ {row['r$']:,.2f}"):
                
                det = df_pay[(df_pay['mes_ref'] == row['mes_ref']) & (df_pay['colaborador_email'] == row['colaborador_email'])]
                
                st.dataframe(
                    det[['descricao', 'data_atividade', 'projeto', 'horas', 'r$']], 
                    use_container_width=True, 
                    hide_index=True,
                    column_config={
                        "r$": st.column_config.NumberColumn("Valor (R$)", format="R$ %.2f"),
                        "horas": st.column_config.NumberColumn("HH.MM", format="%.2f"),
                        "data_atividade": st.column_config.DateColumn("Data Real")
                    }
                )
                
                # Controle de Status Individual do Grupo
                s_atual = det['status_pagamento'].iloc[0] if 'status_pagamento' in det.columns else "Em aberto"
                opcoes_p = ["Em aberto", "Pago", "Parcial"]
                idx_p = opcoes_p.index(s_atual) if s_atual in opcoes_p else 0
                
                c_sel, c_b = st.columns([3, 1])
                new_s = c_sel.selectbox(f"Status do Pagamento", options=opcoes_p, index=idx_p, key=f"pay_{idx}")
                
                if c_b.button(f"Confirmar Baixa", key=f"btn_pay_{idx}"):
                    with conn.session as s:
                        # Atualiza todos os IDs daquele grupo (mes+colaborador)
                        # Isso é melhor que atualizar por query genérica
                        ids_group = tuple(det['id'].tolist())
                        s.execute(
                            text("UPDATE lancamentos SET status_pagamento = :s WHERE id IN :ids"),
                            {"s": new_s, "ids": ids_group}
                        )
                        s.commit()
                    st.success("Status atualizado!")
                    time.sleep(0.5); st.rerun()
    else:
        st.info("Não há lançamentos aprovados para gerar pagamentos.")

# ==============================================================================
# ABA 5: BI ESTRATÉGICO (NORMALIZADO E FILTRADO)
# ==============================================================================
elif escolha == "📈 BI Estratégico":
    st.subheader("📈 Inteligência de Custos e Produtividade")
    
    df_bi = df_lan.copy()
    
    # Filtros de BI
    c1, c2 = st.columns(2)
    d_ini = c1.date_input("De (Data Atividade):", datetime.now() - timedelta(days=60))
    d_fim = c2.date_input("Até (Data Atividade):", datetime.now())
    
    # Filtra
    df_bi = df_bi[(df_bi['data_atividade'] >= d_ini) & (df_bi['data_atividade'] <= d_fim)]
    
    if not df_bi.empty:
        # Normalização de nomes (Backend = Back-end)
        df_bi['tipo_norm'] = df_bi['tipo'].apply(normalize_text_for_bi)
        
        # Cálculos
        df_bi['h_dec'] = df_bi['horas'].apply(convert_to_decimal_hours)
        df_bi["custo"] = df_bi['h_dec'] * df_bi["valor_hora_historico"]
        
        # Scorecards Master
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Horas Totais (HH.MM)", f"{df_bi['horas'].sum():.2f}")
        m2.metric("Custo Total", f"R$ {df_bi['custo'].sum():,.2f}")
        
        # Ticket Médio: Custo Total / Horas Decimais Totais
        ticket = (df_bi['custo'].sum() / df_bi['h_dec'].sum()) if df_bi['h_dec'].sum() > 0 else 0
        m3.metric("Ticket Médio/Hora", f"R$ {ticket:,.2f}")
        m4.metric("Total Registros", len(df_bi))
        
        st.divider()
        
        # Gráficos
        col_g1, col_g2 = st.columns(2)
        with col_g1:
            st.write("**💰 Custo por Projeto**")
            st.bar_chart(df_bi.groupby("projeto")["custo"].sum())
            
        with col_g2:
            st.write("**⏱️ Horas por Tipo de Atividade**")
            # Usa coluna normalizada
            st.bar_chart(df_bi.groupby("tipo_norm")["horas"].sum())
            
        st.write("**🏆 Ranking de Colaboradores (Produtividade)**")
        rank = df_bi.groupby("colaborador_email").agg({'horas': 'sum', 'custo': 'sum'}).sort_values('horas', ascending=False)
        st.dataframe(
            rank, 
            use_container_width=True,
            column_config={
                "custo": st.column_config.NumberColumn("Custo Est. (R$)", format="R$ %.2f"),
                "horas": st.column_config.NumberColumn("Horas (HH.MM)", format="%.2f")
            }
        )
    else:
        st.info("Sem dados para exibir no período selecionado.")

# ==============================================================================
# ABA 6: CONFIGURAÇÕES (COMPLETA, SEM ERROS)
# ==============================================================================
elif escolha == "⚙️ Configurações":
    st.subheader("⚙️ Configurações do Sistema")
    
    # --- 1. USUÁRIOS ---
    st.write("👥 **Gestão de Usuários**")
    st.caption("Defina e-mails, senhas e quem tem acesso Admin.")
    
    # Editor de Usuários (Configurado para não dar erro de senha)
    ed_users = st.data_editor(
        df_u_login, 
        num_rows="dynamic", 
        hide_index=True,
        key="editor_users_config",
        column_config={
            "is_admin": st.column_config.CheckboxColumn("Admin Access?", default=False),
            # Senha como texto simples para editar facilmente (em prod, use hash)
            "senha": st.column_config.TextColumn("Senha (Visível)", width="medium"), 
            "valor_hora": st.column_config.NumberColumn("Valor/Hora", format="R$ %.2f")
        }
    )
    
    if st.button("💾 Salvar Usuários"):
        with conn.session as s:
            for r in ed_users.itertuples():
                # Upsert de Usuários
                s.execute(
                    text("""
                        INSERT INTO usuarios (email, valor_hora, senha, is_admin) 
                        VALUES (:e, :v, :s, :a) 
                        ON CONFLICT (email) 
                        DO UPDATE SET valor_hora=:v, senha=:s, is_admin=:a
                    """),
                    {"e": r.email, "v": r.valor_hora, "s": str(r.senha), "a": bool(r.is_admin)}
                )
            s.commit()
        st.success("Tabela de usuários atualizada com sucesso!")
        time.sleep(0.5); st.rerun()

    st.divider()

    # --- 2. PROJETOS ---
    st.write("📁 **Gestão de Projetos**")
    st.caption("Cadastre projetos para aparecerem no formulário de lançamentos.")
    
    ed_projs = st.data_editor(
        df_projs, 
        num_rows="dynamic", 
        hide_index=True,
        key="editor_projs_config"
    )
    
    if st.button("💾 Salvar Projetos"):
        with conn.session as s:
            for r in ed_projs.itertuples():
                if r.nome:
                    s.execute(text("INSERT INTO projetos (nome) VALUES (:n) ON CONFLICT (nome) DO NOTHING"), {"n": r.nome})
            s.commit()
        st.success("Lista de projetos atualizada!")
        time.sleep(0.5); st.rerun()

    st.divider()

    # --- 3. DADOS BANCÁRIOS ---
    st.write("🏦 **Dados Bancários**")
    st.caption("Cadastre o PIX ou conta dos colaboradores para facilitar o pagamento.")
    
    ed_banks = st.data_editor(
        df_banc, 
        num_rows="dynamic", 
        hide_index=True, 
        key="editor_banks_config",
        column_config={
            "tipo_chave": st.column_config.SelectboxColumn(
                "Tipo Chave", 
                options=["CPF", "CNPJ", "Email", "Celular", "Aleatoria", "Agencia/Conta"],
                required=True
            )
        }
    )
    
    if st.button("💾 Salvar Dados Bancários"):
        with conn.session as s:
            for r in ed_banks.itertuples():
                # Tratamento de segurança para garantir que tipo_chave nunca vá nulo
                tc = getattr(r, 'tipo_chave', 'CPF')
                if not tc: tc = 'CPF'
                
                s.execute(
                    text("""
                        INSERT INTO dados_bancarios (colaborador_email, banco, tipo_chave, chave_pix) 
                        VALUES (:e, :b, :t, :c) 
                        ON CONFLICT (colaborador_email) 
                        DO UPDATE SET banco=:b, tipo_chave=:t, chave_pix=:c
                    """),
                    {"e": r.colaborador_email, "b": r.banco, "t": tc, "c": r.chave_pix}
                )
            s.commit()
        st.success("Dados bancários salvos!")

# ==============================================================================
# RODAPÉ
# ==============================================================================
st.markdown("---")
st.markdown(
    "<p style='text-align: center; color: gray; font-size: 12px;'>"
    "OnCall Humana - Developed by Pedro Reis | v6.6 Colossus Edition | "
    f"Status: Online | {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    "</p>", 
    unsafe_allow_html=True
)