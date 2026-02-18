import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import uuid
import time
import io
from sqlalchemy import text

# ==============================================================================
# 1. CONFIGURAÇÃO DA PÁGINA E ESTILO
# ==============================================================================
st.set_page_config(
    page_title="OnCall Humana - Master v6.2", 
    layout="wide", 
    page_icon="🛡️"
)

# ==============================================================================
# 2. CONEXÃO COM O BANCO DE DADOS (NEON POSTGRES)
# ==============================================================================
def get_connection():
    """Estabelece conexão segura e persistente com o banco."""
    try:
        c = st.connection("postgresql", type="sql")
        # Query leve para 'acordar' o banco serverless se estiver dormindo
        c.query("SELECT 1", ttl=0) 
        return c
    except Exception as e:
        st.error(f"Erro Crítico de Conexão com o Banco de Dados: {e}")
        st.stop()

conn = get_connection()

# ==============================================================================
# 3. LÓGICA DE NEGÓCIO E UTILITÁRIOS
# ==============================================================================
def convert_to_decimal_hours(pseudo_hour):
    """
    Converte formato humano HH.MM para decimal financeiro.
    Ex: 2.30 (2h30min) -> 2.50 (decimal)
    Ex: 2.50 (2h50min) -> 2.83 (decimal)
    """
    try:
        val_str = f"{float(pseudo_hour):.2f}"
        horas_inteiras, minutos = map(int, val_str.split('.'))
        # Regra de proteção: se minutos > 59, trata como erro ou ajuste
        if minutos >= 60:
            return float(pseudo_hour) # Retorna o original se parecer decimal puro
        return horas_inteiras + (minutos / 60)
    except:
        return 0.0

def normalize_text(text_val):
    """Padroniza nomes para evitar duplicidade nos gráficos (Ex: Backend -> Back-end)"""
    if not isinstance(text_val, str): return text_val
    t = text_val.strip().lower()
    if "back" in t and "end" in t: return "Back-end"
    if "front" in t and "end" in t: return "Front-end"
    if "infra" in t: return "Infraestrutura"
    return text_val.capitalize()

# ==============================================================================
# 4. FUNÇÕES DE LEITURA DE DADOS (SEM CACHE PARA DADOS REAIS)
# ==============================================================================
def get_all_data(): 
    return conn.query("SELECT * FROM lancamentos ORDER BY data_registro DESC", ttl=0)

def get_config_users(): 
    return conn.query("SELECT * FROM usuarios", ttl=0)

def get_config_projs(): 
    return conn.query("SELECT * FROM projetos", ttl=0)

def get_bancos(): 
    return conn.query("SELECT * FROM dados_bancarios", ttl=0)

# ==============================================================================
# 5. AUTENTICAÇÃO E PERMISSÕES
# ==============================================================================
df_u_login = get_config_users()
# Dicionário mestre de usuários
dict_users = {row.email: {
    "valor": float(row.valor_hora), 
    "senha": str(row.senha), 
    "is_admin": bool(getattr(row, 'is_admin', False)) 
} for row in df_u_login.itertuples()}

SUPER_ADMINS = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]

# Sidebar de Login
st.sidebar.title("🛡️ OnCall Humana")
st.sidebar.caption("v6.2 Enterprise Leviathan")

user_email = st.sidebar.selectbox("👤 Usuário:", ["..."] + list(dict_users.keys()))

if user_email == "...":
    st.info("👈 Por favor, selecione seu usuário no menu lateral para iniciar.")
    st.stop()

senha_input = st.sidebar.text_input("🔑 Senha:", type="password")

if senha_input != dict_users[user_email]["senha"]:
    st.sidebar.warning("Senha incorreta.")
    st.stop()

# Define nível de acesso
is_user_admin = dict_users[user_email]["is_admin"] or user_email in SUPER_ADMINS

# ==============================================================================
# 6. NAVEGAÇÃO PERSISTENTE
# ==============================================================================
st.sidebar.divider()
st.sidebar.subheader("📍 Navegação")

if is_user_admin:
    menu_options = [
        "📝 Lançamentos", 
        "📊 Meu Painel", 
        "🛡️ Admin Aprovações", 
        "💸 Pagamentos", 
        "📈 BI Estratégico", 
        "⚙️ Configurações"
    ]
else:
    menu_options = ["📝 Lançamentos", "📊 Meu Painel"]

escolha = st.sidebar.radio("Ir para:", menu_options)

# ==============================================================================
# 7. CARREGAMENTO DE DADOS GLOBAIS
# ==============================================================================
df_lan = get_all_data()
df_projs = get_config_projs()
df_banc = get_bancos()

# Tratamento de listas vazias
lista_projetos = df_projs['nome'].tolist() if not df_projs.empty else ["Sustentação", "Projetos", "Outros"]
colaboradores = sorted(df_lan['colaborador_email'].unique()) if not df_lan.empty else []

# ==============================================================================
# ABA 1: LANÇAMENTOS (INDIVIDUAL)
# ==============================================================================
if escolha == "📝 Lançamentos":
    st.subheader("📝 Registro Individual de Atividade")
    st.caption("Nota: Utilize o formato HH.MM (Ex: 1.30 = 1h30min). O sistema fará a conversão financeira automaticamente.")
    
    with st.form("form_lancamento", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        
        proj_sel = c1.selectbox("Projeto", lista_projetos)
        tipo_sel = c2.selectbox("Tipo de Atividade", ["Front-end", "Back-end", "Infra", "QA", "Dados", "Reunião", "Gestão", "Design"])
        data_sel = c3.date_input("Data da Atividade", datetime.now())
        
        c4, c5 = st.columns([1, 2])
        horas_input = c4.number_input("Horas (HH.MM)", min_value=0.0, step=0.10, format="%.2f")
        desc_input = c5.text_input("Descrição detalhada da entrega")
        
        btn_gravar = st.form_submit_button("🚀 Gravar Lançamento no Banco")
        
        if btn_gravar:
            if horas_input <= 0:
                st.error("As horas devem ser maiores que zero.")
            elif not desc_input:
                st.error("A descrição é obrigatória.")
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
                                "c": data_sel.strftime("%Y-%m"), 
                                "t": tipo_sel, 
                                "d": desc_input, 
                                "v": dict_users[user_email]["valor"]
                            }
                        )
                        s.commit()
                    st.success("Lançamento gravado com sucesso!")
                    time.sleep(0.5)
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao gravar: {e}")

# ==============================================================================
# ABA 2: MEU PAINEL (PESSOAL)
# ==============================================================================
elif escolha == "📊 Meu Painel":
    st.subheader(f"📊 Painel Financeiro - {user_email}")
    
    # Filtros Pessoais
    c_f1, c_f2 = st.columns(2)
    data_ini = c_f1.date_input("Data Início:", datetime.now() - timedelta(days=30))
    data_fim = c_f2.date_input("Data Fim:", datetime.now())
    
    df_m = df_lan[df_lan["colaborador_email"] == user_email].copy()
    
    # Aplica Filtro de Data
    if not df_m.empty:
        df_m['data_registro_dt'] = pd.to_datetime(df_m['data_registro']).dt.date
        df_m = df_m[(df_m['data_registro_dt'] >= data_ini) & (df_m['data_registro_dt'] <= data_fim)]
    
    if not df_m.empty:
        # Cálculos
        df_m['h_dec'] = df_m['horas'].apply(convert_to_decimal_hours)
        df_m['total_r$'] = df_m['h_dec'] * df_m['valor_hora_historico']
        
        # Scorecards de Auditoria Pessoal
        st.write("#### 🔹 Resumo do Período")
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Pendente (h)", f"{df_m[df_m['status_aprovaca'] == 'Pendente']['horas'].sum():.2f}")
        k2.metric("Aprovado (h)", f"{df_m[df_m['status_aprovaca'] == 'Aprovado']['horas'].sum():.2f}")
        k3.metric("Pago (h)", f"{df_m[df_m['status_pagamento'] == 'Pago']['horas'].sum():.2f}")
        k4.metric("Valor Total (R$)", f"R$ {df_m['total_r$'].sum():,.2f}")
        
        st.divider()
        st.write("#### 🔹 Detalhamento")
        
        # Organização de colunas
        cols_view = ['descricao', 'data_registro', 'projeto', 'horas', 'total_r$', 'status_aprovaca', 'status_pagamento']
        
        st.dataframe(
            df_m[cols_view], 
            use_container_width=True, 
            hide_index=True, 
            column_config={
                "total_r$": st.column_config.NumberColumn("Valor Est. (R$)", format="R$ %.2f"),
                "horas": "Horas (HH.MM)",
                "data_registro": st.column_config.DateColumn("Data"),
                "status_aprovaca": "Aprovação",
                "status_pagamento": "Pagamento"
            }
        )
    else:
        st.info("Nenhum lançamento encontrado neste período.")

# ==============================================================================
# ABA 3: ADMIN APROVAÇÕES (GESTAO COMPLETA)
# ==============================================================================
elif escolha == "🛡️ Admin Aprovações":
    st.subheader("🛡️ Central de Gestão Operacional")
    
    # --- BLOCO A: IMPORTAÇÃO EM MASSA (EXPANDER) ---
    with st.expander("📥 Importação em Massa (Copiar e Colar do Excel)"):
        st.markdown("""
        **Instruções:**
        1. Copie as colunas do Excel na seguinte ordem exata:
        2. **Data** | **Projeto** | **E-mail Usuário** | **Horas (HH.MM)** | **Tipo** | **Descrição**
        3. Cole no campo abaixo e clique em confirmar.
        """)
        cola_texto = st.text_area("Cole os dados aqui:", height=150)
        
        if cola_texto:
            try:
                df_paste = pd.read_csv(io.StringIO(cola_texto), sep='\t', names=["data", "projeto", "usuario", "horas", "tipo", "descricao"])
                st.write("📋 **Prévia para Conferência:**")
                st.dataframe(df_paste, use_container_width=True)
                
                if st.button("🚀 Confirmar Importação em Massa"):
                    with conn.session as s:
                        for r in df_paste.itertuples():
                            # Busca valor hora do usuário ou 0 se não existir
                            v_h = dict_users.get(r.usuario, {}).get("valor", 0)
                            # Gera competência YYYY-MM
                            comp_gen = pd.to_datetime(r.data, dayfirst=True).strftime("%Y-%m")
                            
                            s.execute(
                                text("""
                                    INSERT INTO lancamentos 
                                    (id, colaborador_email, projeto, horas, competencia, tipo, descricao, valor_hora_historico) 
                                    VALUES (:id, :e, :p, :h, :c, :t, :d, :v)
                                """),
                                {
                                    "id": str(uuid.uuid4()), 
                                    "e": r.usuario, 
                                    "p": r.projeto, 
                                    "h": r.horas, 
                                    "c": comp_gen, 
                                    "t": r.tipo, 
                                    "d": r.descricao, 
                                    "v": v_h
                                }
                            )
                        s.commit()
                    st.success(f"{len(df_paste)} registros importados com sucesso!")
                    time.sleep(1)
                    st.rerun()
            except Exception as e:
                st.error(f"Erro ao processar dados. Verifique a formatação. Detalhe: {e}")

    st.divider()

    # --- BLOCO B: TABELA DE PENDENTES ---
    st.write("### 🕒 Fila de Pendentes (Avaliação)")
    
    # Filtros Pendentes
    col_fp1, col_fp2 = st.columns([1, 2])
    
    # Lógica de "Selecionar Todos"
    marcar_todos = col_fp1.checkbox("Selecionar Todos os Pendentes")
    
    filtro_colab_p = col_fp2.selectbox("Filtrar por Colaborador:", ["Todos"] + colaboradores, key="filter_pend")
    
    # Prepara DataFrame Pendente
    df_p = df_lan[df_lan['status_aprovaca'] == 'Pendente'].copy()
    if filtro_colab_p != "Todos":
        df_p = df_p[df_p['colaborador_email'] == filtro_colab_p]
    
    # Seleciona colunas (Descrição primeiro, ID último, PROJETO INCLUÍDO)
    df_p = df_p[['descricao', 'projeto', 'colaborador_email', 'data_registro', 'horas', 'tipo', 'id']]
    
    # Insere colunas de controle
    df_p.insert(0, "✅", marcar_todos) # Se marcar_todos for True, tudo vem True
    df_p.insert(1, "🗑️", False)
    
    # Editor de Dados
    ed_p = st.data_editor(
        df_p, 
        use_container_width=True, 
        hide_index=True, 
        key="editor_pendentes",
        column_config={
            "✅": st.column_config.CheckboxColumn("Aprovar", help="Marque para aprovar"),
            "🗑️": st.column_config.CheckboxColumn("Excluir", help="Marque para excluir"),
            "horas": st.column_config.NumberColumn("Horas", format="%.2f"),
            "data_registro": st.column_config.DateColumn("Data")
        }
    )
    
    # Botões de Ação Pendentes
    c_btn1, c_btn2 = st.columns(2)
    
    if c_btn1.button("✔️ APROVAR SELECIONADOS", use_container_width=True):
        ids_to_approve = ed_p[ed_p["✅"] == True]["id"].tolist()
        if ids_to_approve:
            with conn.session as s:
                s.execute(
                    text("UPDATE lancamentos SET status_aprovaca = 'Aprovado' WHERE id IN :ids"), 
                    {"ids": tuple(ids_to_approve)}
                )
                s.commit()
            st.success(f"{len(ids_to_approve)} itens aprovados!")
            time.sleep(0.5)
            st.rerun()
        else:
            st.warning("Nenhum item selecionado para aprovação.")
            
    if c_btn2.button("🔥 EXCLUIR/NEGAR SELECIONADOS", type="primary", use_container_width=True):
        # Aqui podemos decidir se Exclui (DELETE) ou Nega (UPDATE status='Negado')
        # Pela lógica de 'Lixeira', vamos deletar. Se quiser negar, troque para UPDATE.
        # Usuário pediu TABELA DE REJEITADOS, então vamos MUDAR PARA NEGAR.
        
        ids_to_deny = ed_p[ed_p["🗑️"] == True]["id"].tolist()
        if ids_to_deny:
            with conn.session as s:
                s.execute(
                    text("UPDATE lancamentos SET status_aprovaca = 'Negado' WHERE id IN :ids"), 
                    {"ids": tuple(ids_to_deny)}
                )
                s.commit()
            st.warning(f"{len(ids_to_deny)} itens movidos para Rejeitados!")
            time.sleep(0.5)
            st.rerun()
        else:
            st.warning("Nenhum item selecionado para rejeição.")

    st.divider()

    # --- BLOCO C: TABELA DE APROVADOS ---
    st.write("### ✅ Histórico de Aprovados (Edição)")
    
    filtro_colab_a = st.selectbox("Filtrar por Colaborador (Aprovados):", ["Todos"] + colaboradores, key="filter_aprov")
    
    df_a = df_lan[df_lan['status_aprovaca'] == 'Aprovado'].copy()
    if filtro_colab_a != "Todos":
        df_a = df_a[df_a['colaborador_email'] == filtro_colab_a]
        
    df_a = df_a[['descricao', 'projeto', 'colaborador_email', 'data_registro', 'horas', 'status_aprovaca', 'id']]
    
    ed_a = st.data_editor(
        df_a, 
        use_container_width=True, 
        hide_index=True, 
        key="editor_aprovados",
        column_config={
            "status_aprovaca": st.column_config.SelectboxColumn("Status", options=["Aprovado", "Pendente", "Negado"], required=True),
            "horas": st.column_config.NumberColumn("Horas (HH.MM)", format="%.2f")
        }
    )
    
    if st.button("💾 Salvar Alterações em Aprovados"):
        with conn.session as s:
            for r in ed_a.itertuples():
                s.execute(
                    text("UPDATE lancamentos SET status_aprovaca = :s, horas = :h, descricao = :d, projeto = :p WHERE id = :id"), 
                    {"s": r.status_aprovaca, "h": r.horas, "d": r.descricao, "p": r.projeto, "id": r.id}
                )
            s.commit()
        st.success("Alterações salvas!")
        time.sleep(0.5)
        st.rerun()

    st.divider()

    # --- BLOCO D: TABELA DE REJEITADOS (NEGADOS) ---
    st.write("### ❌ Lançamentos Rejeitados")
    st.caption("Itens negados ficam aqui. Você pode alterar o status para 'Pendente' para recuperá-los.")
    
    df_n = df_lan[df_lan['status_aprovaca'] == 'Negado'].copy()
    
    if not df_n.empty:
        df_n = df_n[['descricao', 'projeto', 'colaborador_email', 'data_registro', 'horas', 'status_aprovaca', 'id']]
        
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
        if col_n1.button("💾 Recuperar/Salvar Rejeitados"):
            with conn.session as s:
                for r in ed_n.itertuples():
                    if r.status_aprovaca != 'Negado': # Só atualiza se mudou
                        s.execute(text("UPDATE lancamentos SET status_aprovaca = :s WHERE id = :id"), {"s": r.status_aprovaca, "id": r.id})
                s.commit()
            st.rerun()
            
        if col_n2.button("🔥 EXCLUIR DEFINITIVAMENTE DO BANCO", type="primary"):
            # Exclusão Real
            ids_real_del = ed_n['id'].tolist()
            if ids_real_del:
                with conn.session as s:
                    s.execute(text("DELETE FROM lancamentos WHERE id IN :ids AND status_aprovaca = 'Negado'"), {"ids": tuple(ids_real_del)})
                    s.commit()
                st.warning("Itens excluídos permanentemente.")
                st.rerun()
    else:
        st.info("Nenhum lançamento rejeitado no momento.")

# ==============================================================================
# ABA 4: PAGAMENTOS (DRILL-DOWN COM CÁLCULO REAL)
# ==============================================================================
elif escolha == "💸 Pagamentos":
    st.subheader("💸 Consolidação de Pagamentos")
    
    df_pay = df_lan[df_lan['status_aprovaca'] == 'Aprovado'].copy()
    
    if not df_pay.empty:
        # Conversão de horas e cálculo
        df_pay['h_dec'] = df_pay['horas'].apply(convert_to_decimal_hours)
        df_pay['r$'] = df_pay['h_dec'] * df_pay['valor_hora_historico']
        
        # Agrupamento
        df_g = df_pay.groupby(['competencia', 'colaborador_email']).agg({'r$': 'sum', 'horas': 'sum'}).reset_index()
        
        st.write(f"Total a Pagar (Geral): **R$ {df_pay[df_pay['status_pagamento'] != 'Pago']['r$'].sum():,.2f}**")
        
        for idx, row in df_g.iterrows():
            with st.expander(f"📅 {row['competencia']} | 👤 {row['colaborador_email']} | Total: R$ {row['r$']:,.2f}"):
                
                # Detalhe do Grupo
                det = df_pay[(df_pay['competencia'] == row['competencia']) & (df_pay['colaborador_email'] == row['colaborador_email'])]
                
                st.dataframe(
                    det[['descricao', 'data_registro', 'projeto', 'horas', 'r$']], 
                    use_container_width=True, 
                    hide_index=True,
                    column_config={
                        "r$": st.column_config.NumberColumn("Valor (R$)", format="R$ %.2f"),
                        "horas": "Horas (HH.MM)"
                    }
                )
                
                # Controle de Status
                status_atual = det['status_pagamento'].iloc[0] if 'status_pagamento' in det.columns else "Em aberto"
                opcoes_status = ["Em aberto", "Pago", "Parcial"]
                
                idx_status = 0
                if status_atual in opcoes_status:
                    idx_status = opcoes_status.index(status_atual)
                
                c_sel, c_btn = st.columns([3, 1])
                new_status = c_sel.selectbox(f"Status do Pagamento ({idx})", options=opcoes_status, index=idx_status, key=f"pay_sel_{idx}")
                
                if c_btn.button(f"Confirmar {idx}", key=f"btn_pay_{idx}"):
                    with conn.session as s:
                        s.execute(
                            text("UPDATE lancamentos SET status_pagamento = :s WHERE competencia = :c AND colaborador_email = :e AND status_aprovaca = 'Aprovado'"),
                            {"s": new_status, "c": row['competencia'], "e": row['colaborador_email']}
                        )
                        s.commit()
                    st.success("Status atualizado!")
                    time.sleep(0.5)
                    st.rerun()
    else:
        st.info("Não há lançamentos aprovados para gerar pagamentos.")

# ==============================================================================
# ABA 5: BI ESTRATÉGICO (NORMALIZADO)
# ==============================================================================
elif escolha == "📈 BI Estratégico":
    st.subheader("📈 Inteligência de Custos e Produtividade")
    
    df_bi = df_lan.copy()
    
    if not df_bi.empty:
        # Normalização de Texto para Gráficos
        df_bi['tipo_norm'] = df_bi['tipo'].apply(normalize_text)
        
        # Cálculos Financeiros
        df_bi['h_dec'] = df_bi['horas'].apply(convert_to_decimal_hours)
        df_bi["custo"] = df_bi['h_dec'] * df_bi["valor_hora_historico"]
        
        # Scorecards Master
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Horas (HH.MM)", f"{df_bi['horas'].sum():.2f}")
        m2.metric("Custo Total", f"R$ {df_bi['custo'].sum():,.2f}")
        m3.metric("Ticket Médio / Hora", f"R$ {(df_bi['custo'].sum() / df_bi['h_dec'].sum()):,.2f}" if df_bi['h_dec'].sum() > 0 else "0")
        m4.metric("Total Registros", len(df_bi))
        
        st.divider()
        
        # Gráficos
        col_g1, col_g2 = st.columns(2)
        
        with col_g1:
            st.write("**💰 Custo por Projeto**")
            st.bar_chart(df_bi.groupby("projeto")["custo"].sum())
            
        with col_g2:
            st.write("**⏱️ Horas por Tipo de Atividade**")
            # Usa a coluna normalizada para evitar 'Backend' e 'Back-end' duplicados
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

# ==============================================================================
# ABA 6: CONFIGURAÇÕES (BANCOS, USUÁRIOS, PROJETOS)
# ==============================================================================
elif escolha == "⚙️ Configurações":
    st.subheader("⚙️ Configurações do Sistema")
    
    # --- BLOCO BANCOS ---
    st.write("🏦 **Dados Bancários dos Colaboradores**")
    st.caption("Cadastre aqui as chaves PIX ou dados de conta.")
    
    # Adicionando coluna tipo_chave se não existir no visual
    # O banco já tem, mas garantimos que o editor mostre
    
    new_b = st.data_editor(
        df_banc, 
        num_rows="dynamic", 
        hide_index=True, 
        key="editor_bancos",
        column_config={
            "tipo_chave": st.column_config.SelectboxColumn("Tipo Chave", options=["CPF", "CNPJ", "Email", "Celular", "Aleatoria", "Conta Bancaria"], required=True)
        }
    )
    
    if st.button("💾 Salvar Dados Bancários"):
        with conn.session as s:
            for r in new_b.itertuples():
                # Tratamento para garantir que tipo_chave exista
                t_chave = getattr(r, 'tipo_chave', 'CPF')
                s.execute(
                    text("""
                        INSERT INTO dados_bancarios (colaborador_email, banco, tipo_chave, chave_pix) 
                        VALUES (:e, :b, :t, :c) 
                        ON CONFLICT (colaborador_email) 
                        DO UPDATE SET banco=:b, tipo_chave=:t, chave_pix=:c
                    """), 
                    {"e": r.colaborador_email, "b": r.banco, "t": t_chave, "c": r.chave_pix}
                )
            s.commit()
        st.success("Dados bancários salvos com sucesso!")
    
    st.divider()
    
    # --- BLOCO USUÁRIOS E PROJETOS ---
    c_user, c_proj = st.columns(2)
    
    with c_user:
        st.write("👥 **Gestão de Usuários**")
        st.caption("Marque 'is_admin' para dar acesso total.")
        
        new_u = st.data_editor(
            df_u_login, 
            num_rows="dynamic", 
            hide_index=True,
            column_config={
                "senha": st.column_config.TextColumn("Senha", type="password"),
                "is_admin": st.column_config.CheckboxColumn("É Admin?")
            }
        )
        
        if st.button("💾 Salvar Usuários"):
            with conn.session as s:
                for r in new_u.itertuples():
                    s.execute(
                        text("""
                            INSERT INTO usuarios (email, valor_hora, senha, is_admin) 
                            VALUES (:e, :v, :s, :a) 
                            ON CONFLICT (email) 
                            DO UPDATE SET valor_hora=:v, senha=:s, is_admin=:a
                        """), 
                        {"e": r.email, "v": r.valor_hora, "s": r.senha, "a": r.is_admin}
                    )
                s.commit()
            st.success("Usuários atualizados!")
            time.sleep(0.5)
            st.rerun()

    with c_proj:
        st.write("📁 **Cadastro de Projetos**")
        st.caption("Novos projetos aparecerão nos formulários.")
        
        new_p = st.data_editor(df_projs, num_rows="dynamic", hide_index=True)
        
        if st.button("💾 Salvar Projetos"):
            with conn.session as s:
                for r in new_p.itertuples():
                    s.execute(
                        text("INSERT INTO projetos (nome) VALUES (:n) ON CONFLICT (nome) DO NOTHING"), 
                        {"n": r.nome}
                    )
                s.commit()
            st.success("Projetos cadastrados!")
            time.sleep(0.5)
            st.rerun()

# ==============================================================================
# RODAPÉ
# ==============================================================================
st.markdown("---")
st.markdown(
    "<p style='text-align: center; color: gray; font-size: 12px;'>"
    "OnCall Humana - Developed by Pedro Reis | v6.2 Leviathan Edition | "
    f"Database Status: Connected | {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    "</p>", 
    unsafe_allow_html=True
)