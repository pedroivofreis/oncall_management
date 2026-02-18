import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import uuid
import time
import io
from sqlalchemy import text

# ==============================================================================
# 1. CONFIGURAÇÃO DA PÁGINA E ESTILIZAÇÃO
# ==============================================================================
st.set_page_config(
    page_title="OnCall Humana - Master v6.8", 
    layout="wide", 
    page_icon="🛡️",
    initial_sidebar_state="expanded"
)

# CSS para garantir que Scorecards e Tabelas fiquem legíveis em qualquer tema
st.markdown("""
<style>
    /* Ajuste de Padding */
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 3rem;
    }
    /* Estilo de Métricas */
    div[data-testid="stMetric"] {
        border: 1px solid rgba(128, 128, 128, 0.2);
        padding: 10px;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    /* Headers de Expander mais visíveis */
    .streamlit-expanderHeader {
        font-weight: 600;
        font-size: 1.05rem;
    }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 2. CONEXÃO COM O BANCO DE DADOS (POSTGRES NEON)
# ==============================================================================
def get_connection():
    """
    Estabelece conexão segura com o banco de dados.
    Implementa 'wake-up' query para evitar latência inicial em bancos serverless.
    """
    try:
        c = st.connection("postgresql", type="sql")
        c.query("SELECT 1", ttl=0) 
        return c
    except Exception as e:
        st.error(f"🔴 Erro Crítico de Conexão com o Banco de Dados: {e}")
        st.stop()

conn = get_connection()

# ==============================================================================
# 3. UTILITÁRIOS E LÓGICA DE NEGÓCIO
# ==============================================================================

def convert_to_decimal_hours(pseudo_hour):
    """
    Converte o formato visual HH.MM (Ex: 2.30 = 2h 30min) para Decimal (2.50).
    Essencial para cálculo financeiro correto.
    """
    try:
        if pd.isna(pseudo_hour): return 0.0
        
        # Garante formatação string com 2 casas
        val_str = f"{float(pseudo_hour):.2f}"
        parts = val_str.split('.')
        
        horas_inteiras = int(parts[0])
        minutos = int(parts[1])
        
        # Proteção: Se minutos >= 60, assume que o usuário já digitou decimal
        if minutos >= 60:
            return float(pseudo_hour)
            
        # Conversão real: Minutos / 60
        horas_decimais = horas_inteiras + (minutos / 60)
        return horas_decimais
    except Exception:
        return 0.0

def normalize_text_for_bi(text_val):
    """
    Padroniza nomes de Tipos e Projetos para limpeza do BI.
    Evita que 'Backend' e 'Back-end' apareçam como duas barras no gráfico.
    """
    if not isinstance(text_val, str): return text_val
    t = text_val.strip().lower()
    
    if "back" in t and "end" in t: return "Back-end"
    if "front" in t and "end" in t: return "Front-end"
    if "dados" in t or "data" in t: return "Eng. Dados"
    if "infra" in t: return "Infraestrutura"
    if "qa" in t or "test" in t: return "QA / Testes"
    
    return text_val.capitalize()

# ==============================================================================
# 4. FUNÇÕES DE CARREGAMENTO (SEM CACHE PARA DADOS EM TEMPO REAL)
# ==============================================================================
def get_all_data(): 
    """Traz todos os lançamentos ordenados."""
    return conn.query("SELECT * FROM lancamentos ORDER BY competencia DESC, data_registro DESC", ttl=0)

def get_config_users(): 
    """Traz tabela de usuários."""
    return conn.query("SELECT * FROM usuarios", ttl=0)

def get_config_projs(): 
    """Traz tabela de projetos."""
    return conn.query("SELECT * FROM projetos", ttl=0)

def get_bancos(): 
    """Traz dados bancários."""
    return conn.query("SELECT * FROM dados_bancarios", ttl=0)

# ==============================================================================
# 5. SISTEMA DE AUTENTICAÇÃO
# ==============================================================================
df_u_login = get_config_users()

# Dicionário de acesso rápido
dict_users = {row.email: {
    "valor": float(row.valor_hora), 
    "senha": str(row.senha), 
    "is_admin": bool(getattr(row, 'is_admin', False)) 
} for row in df_u_login.itertuples()}

SUPER_ADMINS = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]

# --- SIDEBAR LOGIN ---
st.sidebar.title("🛡️ OnCall Humana")
st.sidebar.caption("System v6.8 Infinity")

user_email = st.sidebar.selectbox("👤 Identificação:", ["..."] + list(dict_users.keys()))

if user_email == "...":
    st.info("👈 Selecione seu usuário para iniciar.")
    st.stop()

senha_input = st.sidebar.text_input("🔑 Senha:", type="password")

if senha_input != dict_users[user_email]["senha"]:
    st.sidebar.warning("Aguardando senha correta...")
    st.stop()

# Definição de Permissão
is_user_admin = dict_users[user_email]["is_admin"] or user_email in SUPER_ADMINS

if is_user_admin:
    st.sidebar.success(f"Logado como ADMIN: {user_email.split('@')[0]}")
else:
    st.sidebar.info(f"Bem-vindo, {user_email.split('@')[0]}")

# ==============================================================================
# 6. MENU DE NAVEGAÇÃO
# ==============================================================================
st.sidebar.divider()
st.sidebar.subheader("📍 Navegação")

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

escolha = st.sidebar.radio("Ir para:", menu_options)

# ==============================================================================
# 7. CARREGAMENTO E PROCESSAMENTO DE DADOS (DATAS)
# ==============================================================================
df_lan = get_all_data()
df_projs = get_config_projs()
df_banc = get_bancos()

lista_projetos = df_projs['nome'].tolist() if not df_projs.empty else ["Sustentação", "Projetos"]
colaboradores = sorted(df_lan['colaborador_email'].unique()) if not df_lan.empty else []

# --- TRATAMENTO CRÍTICO DE DATAS ---
# O sistema precisa diferenciar Data de Registro (Log) de Data da Atividade (Competência)
if not df_lan.empty:
    # 1. Tenta converter 'competencia' para data real YYYY-MM-DD
    # Isso é fundamental para que os filtros de data funcionem no dia exato
    df_lan['data_atividade_dt'] = pd.to_datetime(df_lan['competencia'], errors='coerce').dt.date
    
    # 2. Converte 'data_registro' para data simples
    df_lan['data_importacao_dt'] = pd.to_datetime(df_lan['data_registro']).dt.date
    
    # 3. Fallback: Se competencia for inválida/nula, usa a data de registro
    df_lan['data_atividade_dt'] = df_lan['data_atividade_dt'].fillna(df_lan['data_importacao_dt'])

# ==============================================================================
# ABA 1: LANÇAMENTOS
# ==============================================================================
if escolha == "📝 Lançamentos":
    st.subheader("📝 Registro Individual de Atividades")
    
    with st.expander("ℹ️ Como preencher corretamente?", expanded=False):
        st.markdown("""
        * **Projeto:** Selecione onde você trabalhou.
        * **Tipo:** Classifique a atividade.
        * **Data Real:** O dia que você *executou* a tarefa (não hoje).
        * **Horas:** Use ponto para minutos. Ex: `1.30` = 1h 30min.
        """)
    
    with st.form("form_lancamento_main", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        
        proj_sel = c1.selectbox("Projeto", lista_projetos)
        tipo_sel = c2.selectbox("Tipo de Atividade", ["Front-end", "Back-end", "Infra", "QA", "Dados", "Reunião", "Gestão", "Design", "Apoio"])
        # Campo Vital: Data da Atividade
        data_sel = c3.date_input("Data Real da Atividade", datetime.now())
        
        c4, c5 = st.columns([1, 2])
        horas_input = c4.number_input("Horas Trabalhadas (HH.MM)", min_value=0.0, step=0.10, format="%.2f")
        desc_input = c5.text_input("Descrição detalhada (O que foi entregue?)")
        
        btn_gravar = st.form_submit_button("🚀 Gravar Lançamento")
        
        if btn_gravar:
            if horas_input > 0 and desc_input:
                try:
                    with conn.session as s:
                        s.execute(
                            text("""
                                INSERT INTO lancamentos (id, colaborador_email, projeto, horas, competencia, tipo, descricao, valor_hora_historico) 
                                VALUES (:id, :e, :p, :h, :c, :t, :d, :v)
                            """),
                            {
                                "id": str(uuid.uuid4()), 
                                "e": user_email, 
                                "p": proj_sel, 
                                "h": horas_input, 
                                # Salvamos YYYY-MM-DD na coluna competencia
                                "c": data_sel.strftime("%Y-%m-%d"), 
                                "t": tipo_sel, 
                                "d": desc_input, 
                                "v": dict_users[user_email]["valor"]
                            }
                        )
                        s.commit()
                    st.success(f"Atividade de {horas_input}h em {data_sel.strftime('%d/%m')} salva com sucesso!")
                    time.sleep(0.5); st.rerun()
                except Exception as e:
                    st.error(f"Erro ao salvar: {e}")
            else:
                st.error("Por favor, preencha as horas (> 0) e a descrição.")

# ==============================================================================
# ABA 2: MEU PAINEL (VISÃO ADMIN INTEGRADA)
# ==============================================================================
elif "Meu Painel" in escolha:
    st.subheader("📊 Painel Financeiro")
    
    # 1. Definição do Usuário Alvo
    target_user = user_email
    if is_user_admin:
        col_sel, _ = st.columns([1, 3])
        target_user = col_sel.selectbox(
            "👁️ (Admin) Visualizar dados de:", 
            [user_email] + [c for c in colaboradores if c != user_email]
        )
    
    # 2. Filtros de Data (Baseado na Data Real da Atividade)
    st.write("---")
    c_f1, c_f2 = st.columns(2)
    
    # Padrão: Últimos 30 dias até hoje
    default_ini = datetime.now() - timedelta(days=30)
    default_fim = datetime.now()
    
    data_ini = c_f1.date_input("Filtrar De (Data Atividade):", default_ini)
    data_fim = c_f2.date_input("Filtrar Até (Data Atividade):", default_fim)
    
    # 3. Filtragem do DataFrame
    df_m = df_lan[df_lan["colaborador_email"] == target_user].copy()
    
    if not df_m.empty:
        # Filtra usando a coluna tratada 'data_atividade_dt'
        mask = (df_m['data_atividade_dt'] >= data_ini) & (df_m['data_atividade_dt'] <= data_fim)
        df_m = df_m[mask]
    
    if not df_m.empty:
        # 4. Cálculos Financeiros
        df_m['h_dec'] = df_m['horas'].apply(convert_to_decimal_hours)
        df_m['r$'] = df_m['h_dec'] * df_m['valor_hora_historico']
        
        # 5. Scorecards de Auditoria
        st.markdown(f"### 🔹 Resumo: {target_user}")
        k1, k2, k3, k4 = st.columns(4)
        
        # Somas condicionais
        h_pend = df_m[df_m['status_aprovaca'] == 'Pendente']['horas'].sum()
        h_aprov = df_m[df_m['status_aprovaca'] == 'Aprovado']['horas'].sum()
        h_pago = df_m[df_m['status_pagamento'] == 'Pago']['horas'].sum()
        val_total = df_m['r$'].sum()
        
        k1.metric("Pendente (h)", f"{h_pend:.2f}")
        k2.metric("Aprovado (h)", f"{h_aprov:.2f}")
        k3.metric("Pago (h)", f"{h_pago:.2f}")
        k4.metric("Valor Estimado (R$)", f"R$ {val_total:,.2f}")
        
        st.divider()
        
        # 6. Tabela Detalhada
        st.markdown(f"### 📋 Detalhamento ({len(df_m)} registros)")
        
        # Seleção de Colunas para Exibição
        cols_table = ['descricao', 'data_atividade_dt', 'data_importacao_dt', 'projeto', 'horas', 'r$', 'status_aprovaca', 'status_pagamento']
        
        st.dataframe(
            df_m[cols_table], 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "r$": st.column_config.NumberColumn("Valor (R$)", format="R$ %.2f"),
                "horas": st.column_config.NumberColumn("Horas (HH.MM)", format="%.2f"),
                "data_atividade_dt": st.column_config.DateColumn("Data Atividade", format="DD/MM/YYYY"),
                "data_importacao_dt": st.column_config.DateColumn("Inserido Em", format="DD/MM/YYYY"),
                "descricao": st.column_config.TextColumn("Descrição", width="large"),
                "status_aprovaca": st.column_config.TextColumn("Status Aprovação"),
                "status_pagamento": st.column_config.TextColumn("Pagamento")
            }
        )
    else:
        st.info(f"Nenhum registro encontrado para {target_user} no período selecionado.")

# ==============================================================================
# ABA 3: ADMIN APROVAÇÕES (BIPARTIDA + BULK IMPORT)
# ==============================================================================
elif escolha == "🛡️ Admin Aprovações":
    st.subheader("🛡️ Central de Controle Admin")
    
    # --- BLOCO 1: IMPORTAÇÃO EM MASSA ---
    with st.expander("📥 Importar do Excel (Copiar e Colar)"):
        st.info("O sistema identificará a data correta. Cole as colunas do Excel.")
        st.markdown("**Colunas Obrigatórias:** Data (DD/MM/AAAA) | Projeto | E-mail | Horas | Tipo | Descrição")
        
        cola = st.text_area("Cole os dados aqui:", height=100)
        
        if cola and st.button("🚀 Processar Importação"):
            try:
                # Leitura TSV
                df_p = pd.read_csv(io.StringIO(cola), sep='\t', names=["data", "p", "e", "h", "t", "d"])
                
                with conn.session as s:
                    for r in df_p.itertuples():
                        # Busca valor hora
                        v = dict_users.get(r.e, {}).get("valor", 0)
                        
                        # Conversão de Data Crítica (DD/MM/AAAA -> YYYY-MM-DD)
                        try:
                            dt_obj = pd.to_datetime(r.data, dayfirst=True)
                            dt_save = dt_obj.strftime("%Y-%m-%d")
                        except:
                            # Fallback para hoje se a data estiver zoada
                            dt_save = datetime.now().strftime("%Y-%m-%d")
                            
                        s.execute(
                            text("""
                                INSERT INTO lancamentos (id, colaborador_email, projeto, horas, competencia, tipo, descricao, valor_hora_historico) 
                                VALUES (:id, :e, :p, :h, :c, :t, :d, :v)
                            """),
                            {"id": str(uuid.uuid4()), "e": r.e, "p": r.p, "h": r.h, "c": dt_save, "t": r.t, "d": r.d, "v": v}
                        )
                    s.commit()
                st.success(f"{len(df_p)} registros importados com datas corrigidas!"); time.sleep(1); st.rerun()
            except Exception as e: 
                st.error(f"Erro na leitura dos dados: {e}")

    st.divider()

    # --- BLOCO 2: TABELA DE PENDENTES ---
    st.markdown("### 🕒 Fila de Pendentes")
    
    c_sel, c_fil = st.columns([1, 3])
    # Funcionalidade "Selecionar Todos"
    check_all = c_sel.checkbox("Selecionar Todos")
    # Filtro por Colaborador
    f_p = c_fil.selectbox("Filtrar Pendentes por:", ["Todos"] + colaboradores, key="fp_admin")
    
    df_p = df_lan[df_lan['status_aprovaca'] == 'Pendente'].copy()
    if f_p != "Todos": df_p = df_p[df_p['colaborador_email'] == f_p]
    
    if not df_p.empty:
        # Prepara colunas para edição
        df_p = df_p[['descricao', 'projeto', 'colaborador_email', 'data_atividade_dt', 'horas', 'tipo', 'id']]
        
        # Insere checkboxes de controle
        df_p.insert(0, "✅", check_all) # Se check_all for True, inicia marcado
        df_p.insert(1, "🗑️", False)
        
        ed_p = st.data_editor(
            df_p, 
            use_container_width=True, 
            hide_index=True, 
            key="ed_pend",
            column_config={
                "✅": st.column_config.CheckboxColumn("Aprovar", width="small"),
                "🗑️": st.column_config.CheckboxColumn("Excluir", width="small"),
                "data_atividade_dt": st.column_config.DateColumn("Data Atividade"),
                "horas": st.column_config.NumberColumn("HH.MM", format="%.2f"),
                "descricao": st.column_config.TextColumn("Descrição", width="large")
            }
        )
        
        c1, c2 = st.columns(2)
        if c1.button("✔️ APROVAR SELECIONADOS", use_container_width=True):
            ids = ed_p[ed_p["✅"] == True]["id"].tolist()
            if ids:
                with conn.session as s:
                    s.execute(text("UPDATE lancamentos SET status_aprovaca = 'Aprovado' WHERE id IN :ids"), {"ids": tuple(ids)})
                    s.commit()
                st.success(f"{len(ids)} itens aprovados!"); time.sleep(0.5); st.rerun()
                
        if c2.button("🔥 NEGAR SELECIONADOS", type="primary", use_container_width=True):
            ids = ed_p[ed_p["🗑️"] == True]["id"].tolist()
            if ids:
                with conn.session as s:
                    # Move para Negado (Rejeitados)
                    s.execute(text("UPDATE lancamentos SET status_aprovaca = 'Negado' WHERE id IN :ids"), {"ids": tuple(ids)})
                    s.commit()
                st.warning(f"{len(ids)} itens rejeitados."); time.sleep(0.5); st.rerun()
    else:
        st.info("Nenhum item pendente no momento.")

    st.divider()

    # --- BLOCO 3: TABELA DE APROVADOS (EDIÇÃO) ---
    st.markdown("### ✅ Histórico de Aprovados")
    st.caption("Edite aqui itens já aprovados se encontrar erros.")
    
    f_a = st.selectbox("Filtrar Aprovados por:", ["Todos"] + colaboradores, key="fa_admin")
    
    df_a = df_lan[df_lan['status_aprovaca'] == 'Aprovado'].copy()
    if f_a != "Todos": df_a = df_a[df_a['colaborador_email'] == f_a]
    
    if not df_a.empty:
        df_a = df_a[['descricao', 'projeto', 'colaborador_email', 'data_atividade_dt', 'horas', 'status_aprovaca', 'id']]
        
        ed_a = st.data_editor(
            df_a, 
            use_container_width=True, 
            hide_index=True, 
            key="ed_aprov",
            column_config={
                "status_aprovaca": st.column_config.SelectboxColumn("Status", options=["Aprovado", "Pendente", "Negado"], required=True),
                "data_atividade_dt": st.column_config.DateColumn("Data Atividade"),
                "horas": st.column_config.NumberColumn("HH.MM", format="%.2f")
            }
        )
        
        if st.button("💾 Salvar Edições em Aprovados"):
            with conn.session as s:
                for r in ed_a.itertuples():
                    s.execute(
                        text("UPDATE lancamentos SET status_aprovaca = :s, horas = :h, descricao = :d WHERE id = :id"),
                        {"s": r.status_aprovaca, "h": r.horas, "d": r.descricao, "id": r.id}
                    )
                s.commit()
            st.success("Alterações salvas!"); st.rerun()
    else:
        st.info("Nenhum item aprovado para este filtro.")

    # --- BLOCO 4: REJEITADOS ---
    st.divider()
    with st.expander("❌ Ver Lançamentos Rejeitados / Negados"):
        df_n = df_lan[df_lan['status_aprovaca'] == 'Negado'].copy()
        if not df_n.empty:
            df_n = df_n[['descricao', 'colaborador_email', 'data_atividade_dt', 'status_aprovaca', 'id']]
            
            ed_n = st.data_editor(
                df_n, 
                use_container_width=True, 
                hide_index=True, 
                column_config={
                    "status_aprovaca": st.column_config.SelectboxColumn("Ação", options=["Negado", "Pendente", "Aprovado"])
                }
            )
            
            if st.button("💾 Recuperar Itens Rejeitados"):
                with conn.session as s:
                    for r in ed_n.itertuples():
                        if r.status_aprovaca != "Negado":
                            s.execute(text("UPDATE lancamentos SET status_aprovaca = :s WHERE id = :id"), {"s": r.status_aprovaca, "id": r.id})
                    s.commit()
                st.success("Recuperados!"); st.rerun()
        else:
            st.info("Lixeira vazia.")

# ==============================================================================
# ABA 4: PAGAMENTOS (DRILL-DOWN)
# ==============================================================================
elif escolha == "💸 Pagamentos":
    st.subheader("💸 Consolidação de Pagamentos")
    
    df_pay = df_lan[df_lan['status_aprovaca'] == 'Aprovado'].copy()
    
    if not df_pay.empty:
        # Conversão Financeira
        df_pay['h_dec'] = df_pay['horas'].apply(convert_to_decimal_hours)
        df_pay['r$'] = df_pay['h_dec'] * df_pay['valor_hora_historico']
        
        # Cria Chave de Agrupamento: Mês/Ano da ATIVIDADE
        df_pay['mes_ref'] = pd.to_datetime(df_pay['data_atividade_dt']).dt.strftime('%Y-%m')
        
        # Agrupa
        df_g = df_pay.groupby(['mes_ref', 'colaborador_email']).agg({'r$': 'sum', 'horas': 'sum'}).reset_index()
        
        # Totalizador Topo
        total_open = df_pay[df_pay['status_pagamento'] != 'Pago']['r$'].sum()
        st.metric("Total Pendente de Pagamento (Geral)", f"R$ {total_open:,.2f}")
        
        for idx, row in df_g.iterrows():
            with st.expander(f"📅 {row['mes_ref']} | 👤 {row['colaborador_email']} | Total: R$ {row['r$']:,.2f}"):
                
                det = df_pay[(df_pay['mes_ref'] == row['mes_ref']) & (df_pay['colaborador_email'] == row['colaborador_email'])]
                
                # Tabela Detalhe
                st.dataframe(
                    det[['descricao', 'data_atividade_dt', 'horas', 'r$']], 
                    use_container_width=True, hide_index=True, 
                    column_config={
                        "r$": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
                        "data_atividade_dt": st.column_config.DateColumn("Data"),
                        "horas": st.column_config.NumberColumn("HH.MM", format="%.2f")
                    }
                )
                
                # Controle de Status do Grupo
                s_atual = det['status_pagamento'].iloc[0] if 'status_pagamento' in det.columns else "Em aberto"
                opcoes = ["Em aberto", "Pago", "Parcial"]
                idx_op = opcoes.index(s_atual) if s_atual in opcoes else 0
                
                c_sel, c_btn = st.columns([3, 1])
                new_s = c_sel.selectbox("Status deste grupo", opcoes, index=idx_op, key=f"pay_sel_{idx}")
                
                if c_btn.button("Atualizar Baixa", key=f"pay_btn_{idx}"):
                    with conn.session as s:
                        # Atualiza todos os IDs do grupo
                        ids_g = tuple(det['id'].tolist())
                        s.execute(text("UPDATE lancamentos SET status_pagamento = :s WHERE id IN :ids"), {"s": new_s, "ids": ids_g})
                        s.commit()
                    st.success("Pagamento atualizado!"); st.rerun()
    else:
        st.info("Nenhum lançamento aprovado disponível para pagamento.")

# ==============================================================================
# ABA 5: BI ESTRATÉGICO
# ==============================================================================
elif escolha == "📈 BI Estratégico":
    st.subheader("📈 Inteligência de Negócio")
    
    df_bi = df_lan.copy()
    
    # Filtros de Data BI
    c1, c2 = st.columns(2)
    d_ini = c1.date_input("De (Data Atividade):", datetime.now() - timedelta(days=60))
    d_fim = c2.date_input("Até (Data Atividade):", datetime.now())
    
    # Filtra DF
    df_bi = df_bi[(df_bi['data_atividade_dt'] >= d_ini) & (df_bi['data_atividade_dt'] <= d_fim)]
    
    if not df_bi.empty:
        # Normalização e Cálculo
        df_bi['tipo_norm'] = df_bi['tipo'].apply(normalize_text_for_bi)
        df_bi['h_dec'] = df_bi['horas'].apply(convert_to_decimal_hours)
        df_bi["custo"] = df_bi['h_dec'] * df_bi["valor_hora_historico"]
        
        # Metrics
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Horas Totais", f"{df_bi['horas'].sum():.2f}")
        m2.metric("Custo Operacional", f"R$ {df_bi['custo'].sum():,.2f}")
        
        tkt = (df_bi['custo'].sum() / df_bi['h_dec'].sum()) if df_bi['h_dec'].sum() > 0 else 0
        m3.metric("Ticket Médio/Hora", f"R$ {tkt:,.2f}")
        m4.metric("Volumetria (Registros)", len(df_bi))
        
        st.divider()
        
        # Gráficos
        col_g1, col_g2 = st.columns(2)
        with col_g1:
            st.write("**💰 Custo por Projeto**")
            st.bar_chart(df_bi.groupby("projeto")["custo"].sum())
        with col_g2:
            st.write("**⏱️ Horas por Tipo de Atividade**")
            st.bar_chart(df_bi.groupby("tipo_norm")["horas"].sum())
            
        st.write("**🏆 Ranking de Colaboradores**")
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
        st.info("Sem dados para o período selecionado.")

# ==============================================================================
# ABA 6: CONFIGURAÇÕES
# ==============================================================================
elif escolha == "⚙️ Configurações":
    st.subheader("⚙️ Configurações do Sistema")
    
    # --- USUÁRIOS ---
    st.write("👥 **Gestão de Usuários**")
    # Configuração de Colunas para evitar erro de senha
    ed_u = st.data_editor(
        df_u_login, 
        num_rows="dynamic", 
        hide_index=True,
        column_config={
            "senha": st.column_config.TextColumn("Senha"),
            "is_admin": st.column_config.CheckboxColumn("Admin Access"),
            "valor_hora": st.column_config.NumberColumn("Valor Hora", format="R$ %.2f")
        }
    )
    if st.button("💾 Salvar Usuários"):
        with conn.session as s:
            for r in ed_u.itertuples():
                s.execute(
                    text("INSERT INTO usuarios (email, valor_hora, senha, is_admin) VALUES (:e, :v, :s, :a) ON CONFLICT (email) DO UPDATE SET valor_hora=:v, senha=:s, is_admin=:a"), 
                    {"e": r.email, "v": r.valor_hora, "s": str(r.senha), "a": bool(r.is_admin)}
                )
            s.commit()
        st.success("Usuários salvos!"); st.rerun()
        
    st.divider()
    
    # --- PROJETOS ---
    st.write("📁 **Projetos**")
    ed_p = st.data_editor(df_projs, num_rows="dynamic", hide_index=True)
    if st.button("💾 Salvar Projetos"):
        with conn.session as s:
            for r in ed_p.itertuples():
                if r.nome: s.execute(text("INSERT INTO projetos (nome) VALUES (:n) ON CONFLICT (nome) DO NOTHING"), {"n": r.nome})
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
            "tipo_chave": st.column_config.SelectboxColumn("Tipo Chave", options=["CPF", "CNPJ", "Email", "Aleatoria", "Conta"])
        }
    )
    if st.button("💾 Salvar Bancos"):
        with conn.session as s:
            for r in ed_b.itertuples():
                t_key = getattr(r, 'tipo_chave', 'CPF')
                s.execute(
                    text("INSERT INTO dados_bancarios (colaborador_email, banco, tipo_chave, chave_pix) VALUES (:e, :b, :t, :c) ON CONFLICT (colaborador_email) DO UPDATE SET banco=:b, tipo_chave=:t, chave_pix=:c"), 
                    {"e": r.colaborador_email, "b": r.banco, "t": t_key, "c": r.chave_pix}
                )
            s.commit()
        st.success("Bancos salvos!"); st.rerun()

# ==============================================================================
# RODAPÉ
# ==============================================================================
st.markdown("---")
st.markdown(
    "<p style='text-align: center; color: gray; font-size: 12px;'>"
    "OnCall Humana - Developed by Pedro Reis | v6.8 Infinity Edition | "
    f"Status: Online | {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    "</p>", 
    unsafe_allow_html=True
)