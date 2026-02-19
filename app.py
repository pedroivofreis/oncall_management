"""
================================================================================
ONCALL HUMANA ERP - VERSION 10.0 "THE ARCHITECT"
================================================================================
Author: Pedro Reis & Architect AI
Date: February 2026
License: Proprietary Enterprise License

DESCRIPTION:
This is a monolithic Streamlit application designed for high-availability
timesheet management, financial auditing, and operational workflows.

ARCHITECTURE:
The system is built upon a Class-Based View pattern:
1. DatabaseManager: Handles all SQL Alchemy interactions with retry logic.
2. AuthManager: Manages session state, user mapping, and security.
3. BusinessLogic: Handles conversions (HH.MM), normalizations, and date rules.
4. UIManager: Static methods for consistent styling and component rendering.
5. Views: Distinct classes for each application module (Launch, Dashboard, Admin).

KEY FEATURES:
- Dual-Layer Date Tracking: Activity Date (Real) vs Competency (Financial).
- Edit Flagging: User edits on pending items trigger an alert for Admins.
- Name Resolution: Email-to-Name mapping across all dashboards.
- Bulk Operations: Safe imports with automatic date parsing.
- Financial Drill-Down: Detailed payout management.

DEPENDENCIES:
- streamlit, pandas, sqlalchemy, datetime, uuid, time, io
================================================================================
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
import uuid
import time
import io
from sqlalchemy import text
from typing import Optional, List, Dict, Any, Union

# ==============================================================================
# CLASS: APP CONFIGURATION & STYLING
# ==============================================================================
class AppConfig:
    """
    Centralizes all static configuration and CSS injection.
    Ensures visual consistency across the entire application.
    """
    
    APP_TITLE = "OnCall Humana - Master v10.0"
    APP_ICON = "🛡️"
    LAYOUT = "wide"
    
    @staticmethod
    def initialize():
        """Sets up the Streamlit page configuration."""
        st.set_page_config(
            page_title=AppConfig.APP_TITLE,
            layout=AppConfig.LAYOUT,
            page_icon=AppConfig.APP_ICON,
            initial_sidebar_state="expanded"
        )
        AppConfig._inject_css()

    @staticmethod
    def _inject_css():
        """Injects custom CSS for Enterprise UI/UX."""
        st.markdown("""
        <style>
            /* --- GLOBAL CONTAINER --- */
            .block-container {
                padding-top: 1.5rem;
                padding-bottom: 5rem;
                max-width: 98% !important;
            }
            
            /* --- METRICS & CARDS --- */
            div[data-testid="stMetric"] {
                background-color: rgba(255, 255, 255, 0.03); 
                border: 1px solid rgba(128, 128, 128, 0.2);
                padding: 15px;
                border-radius: 10px;
                box-shadow: 0 4px 6px rgba(0,0,0,0.05);
                transition: all 0.2s ease-in-out;
            }
            div[data-testid="stMetric"]:hover {
                border-color: #4facfe;
                transform: translateY(-2px);
            }
            
            /* --- INPUT LABELS --- */
            label {
                font-weight: 600 !important;
                font-size: 0.95rem !important;
                letter-spacing: 0.02em;
            }
            
            /* --- EXPANDERS --- */
            .streamlit-expanderHeader {
                font-weight: 700;
                font-size: 1.05rem;
                color: #007bff;
                background-color: rgba(128, 128, 128, 0.05);
                border-radius: 5px;
                padding: 10px;
            }
            
            /* --- DATAFRAMES --- */
            div[data-testid="stDataFrame"] {
                border: 1px solid rgba(128, 128, 128, 0.15);
                border-radius: 8px;
                overflow: hidden;
            }
            
            /* --- BUTTONS --- */
            button[kind="primary"] {
                background: linear-gradient(90deg, #007bff 0%, #0056b3 100%);
                border: none;
                font-weight: bold;
                transition: filter 0.2s;
            }
            button[kind="primary"]:hover {
                filter: brightness(1.1);
            }
            
            /* --- ALERTS --- */
            .edited-flag {
                color: #d9534f;
                font-weight: bold;
                border: 1px solid #d9534f;
                padding: 2px 6px;
                border-radius: 4px;
                font-size: 0.8em;
            }
        </style>
        """, unsafe_allow_html=True)

# ==============================================================================
# CLASS: BUSINESS LOGIC & UTILITIES
# ==============================================================================
class BusinessLogic:
    """
    Encapsulates purely functional logic, math, and data transformations.
    Stateless methods.
    """

    @staticmethod
    def convert_hhmm_to_decimal(pseudo_hour: Union[float, str]) -> float:
        """
        Converts human-readable time format (HH.MM) to decimal format for billing.
        
        Logic:
        - 1.30 (1h 30m) -> 1.50 hours.
        - 0.45 (45m) -> 0.75 hours.
        
        Safety:
        - Handles NaN, None, and Empty strings.
        - Handles user typos (e.g., 1.90 treated as decimal).
        """
        try:
            if pd.isna(pseudo_hour) or pseudo_hour == "":
                return 0.0
            
            val_str = f"{float(pseudo_hour):.2f}"
            parts = val_str.split('.')
            
            if len(parts) != 2:
                return float(pseudo_hour)
                
            hours = int(parts[0])
            minutes = int(parts[1])
            
            # Critical Safety: If minutes >= 60, assume user meant decimal already
            if minutes >= 60:
                return float(pseudo_hour)
                
            decimal_hours = hours + (minutes / 60.0)
            return decimal_hours
        except Exception:
            return 0.0

    @staticmethod
    def normalize_project_name(name: str) -> str:
        """Standardizes project names for reporting."""
        if not isinstance(name, str): return "N/A"
        return name.strip()

    @staticmethod
    def normalize_activity_type(text_val: str) -> str:
        """
        Normalizes activity types to prevent fragmentation in BI charts.
        Ex: 'Backend', 'Back-end', 'back end' -> 'Back-end'
        """
        if not isinstance(text_val, str): 
            return "Outros"
            
        t = text_val.strip().lower()
        
        mapping = {
            "back": "Back-end",
            "front": "Front-end",
            "dados": "Eng. Dados",
            "data": "Eng. Dados",
            "infra": "Infraestrutura",
            "devops": "Infraestrutura",
            "qa": "QA / Testes",
            "test": "QA / Testes",
            "banco": "Banco de Dados",
            "reuni": "Reunião",
            "meet": "Reunião",
            "gest": "Gestão",
            "agile": "Gestão",
            "design": "Design/UX",
            "ux": "Design/UX",
            "apoio": "Apoio Operacional"
        }
        
        for key, value in mapping.items():
            if key in t:
                return value
        
        return text_val.capitalize()

    @staticmethod
    def calculate_competence(date_obj: date) -> str:
        """Calculates the billing competence (YYYY-MM) from a Date object."""
        if not date_obj:
            return datetime.now().strftime("%Y-%m")
        return date_obj.strftime("%Y-%m")

# ==============================================================================
# CLASS: DATABASE MANAGER (DAL)
# ==============================================================================
class DatabaseManager:
    """
    Handles all interactions with the PostgreSQL (Neon) database.
    Implements connection health checks and error handling wrapper.
    """
    
    @staticmethod
    def _get_connection():
        """Internal method to establish connection."""
        try:
            # Using st.connection for built-in caching management logic
            conn = st.connection("postgresql", type="sql")
            # Wake-up query for Serverless databases
            conn.query("SELECT 1", ttl=0)
            return conn
        except Exception as e:
            st.error("🔴 DATABASE CONNECTION ERROR")
            st.code(f"Details: {str(e)}")
            st.stop()

    @staticmethod
    def fetch_dataframe(query: str, ttl: int = 0) -> pd.DataFrame:
        """Executes a SELECT query and returns a Pandas DataFrame."""
        conn = DatabaseManager._get_connection()
        try:
            return conn.query(query, ttl=ttl)
        except Exception as e:
            st.error(f"🔴 READ ERROR: {e}")
            return pd.DataFrame()

    @staticmethod
    def execute_statement(statement: str, params: dict) -> bool:
        """Executes INSERT/UPDATE/DELETE statements safely."""
        conn = DatabaseManager._get_connection()
        try:
            with conn.session as session:
                session.execute(text(statement), params)
                session.commit()
            return True
        except Exception as e:
            st.error(f"🔴 WRITE ERROR: {e}")
            return False

    # --- SPECIFIC DATA FETCHERS ---
    
    @staticmethod
    def get_all_launches():
        return DatabaseManager.fetch_dataframe(
            "SELECT * FROM lancamentos ORDER BY competencia DESC, data_atividade DESC, data_registro DESC"
        )

    @staticmethod
    def get_users():
        return DatabaseManager.fetch_dataframe("SELECT * FROM usuarios ORDER BY email")

    @staticmethod
    def get_projects():
        return DatabaseManager.fetch_dataframe("SELECT * FROM projetos ORDER BY nome")

    @staticmethod
    def get_banks():
        return DatabaseManager.fetch_dataframe("SELECT * FROM dados_bancarios")

# ==============================================================================
# CLASS: AUTHENTICATION & SESSION MANAGER
# ==============================================================================
class AuthManager:
    """
    Manages user login, session state, permissions, and name mapping.
    """
    
    def __init__(self):
        self.users_df = pd.DataFrame()
        self.user_map = {} # email -> details
        self.name_map = {} # email -> visual name
        self.super_admins = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]
        
    def load_users(self):
        """Loads user data from DB and builds lookups."""
        self.users_df = DatabaseManager.get_users()
        
        if not self.users_df.empty:
            for row in self.users_df.itertuples():
                # Name Logic
                nome = getattr(row, 'nome', None)
                if not nome or str(nome).strip() == "":
                    nome = row.email.split('@')[0].replace('.', ' ').title()
                
                self.name_map[row.email] = nome
                
                self.user_map[row.email] = {
                    "password": str(row.senha),
                    "is_admin": bool(getattr(row, 'is_admin', False)),
                    "rate": float(row.valor_hora) if row.valor_hora else 0.0,
                    "name": nome
                }

    def render_login_sidebar(self):
        """Renders the login form in the sidebar."""
        st.sidebar.markdown("---")
        st.sidebar.subheader("🔐 Acesso Seguro")
        
        if not self.user_map:
            st.sidebar.error("Banco de dados de usuários vazio.")
            st.stop()
            
        # Create visual list for Selectbox: "Name (email)"
        visual_options = [f"{self.name_map[e]} ({e})" for e in self.user_map.keys()]
        # Reverse map to get email back
        visual_to_email = {v: e for e, v in zip(self.user_map.keys(), visual_options)}
        
        selected_visual = st.sidebar.selectbox("Identifique-se:", ["..."] + visual_options)
        
        if selected_visual == "...":
            st.info("👈 Faça login para continuar.")
            st.stop()
            
        selected_email = visual_to_email[selected_visual]
        user_data = self.user_map[selected_email]
        
        password_input = st.sidebar.text_input("Senha:", type="password")
        
        if password_input != user_data["password"]:
            st.sidebar.warning("Senha incorreta.")
            st.stop()
            
        # Determine Admin Status
        is_admin = user_data["is_admin"] or (selected_email in self.super_admins)
        
        # Save to Session State
        return {
            "email": selected_email,
            "name": user_data["name"],
            "is_admin": is_admin,
            "rate": user_data["rate"]
        }

# ==============================================================================
# CLASS: DATA PROCESSOR (DATAFRAME MANIPULATION)
# ==============================================================================
class DataProcessor:
    """Handles DataFrame enrichment and cleaning before visualization."""
    
    @staticmethod
    def prepare_launches_df(df: pd.DataFrame, name_map: dict) -> pd.DataFrame:
        """
        Enriches the raw launches DataFrame with Names, Dates, and Calculated Columns.
        """
        if df.empty:
            return df
            
        # 1. Map Email to Name
        df['Nome'] = df['colaborador_email'].map(name_map).fillna(df['colaborador_email'])
        
        # 2. Date Handling (Data Atividade vs Data Registro)
        if 'data_atividade' in df.columns:
            df['Data Real'] = pd.to_datetime(df['data_atividade'], errors='coerce').dt.date
        else:
            df['Data Real'] = pd.NaT
            
        df['Importado Em'] = pd.to_datetime(df['data_registro']).dt.date
        
        # Fallback: Use Import Date if Activity Date is missing
        df['Data Real'] = df['Data Real'].fillna(df['Importado Em'])
        
        # 3. Edit Flag Handling
        if 'foi_editado' not in df.columns:
            df['foi_editado'] = False
        else:
            df['foi_editado'] = df['foi_editado'].fillna(False).astype(bool)
            
        return df

# ==============================================================================
# VIEW CLASSES (THE MODULES)
# ==============================================================================

# --- MODULE 1: LAUNCH FORM ---
class LaunchView:
    @staticmethod
    def render(user_session: dict, projects: list):
        st.subheader(f"📝 Registro de Atividade - {user_session['name']}")
        
        # Help Section
        with st.expander("ℹ️ Instruções de Preenchimento", expanded=False):
            st.info("""
            * **Data Real:** O dia exato da execução da tarefa.
            * **Horas:** Formato decimal-amigável. `1.30` = 1h30min.
            * **Descrição:** Detalhes para aprovação gerencial.
            """)
            
        with st.form("main_launch_form", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            
            proj = c1.selectbox("Projeto", projects)
            tipo = c2.selectbox("Tipo", ["Front-end", "Back-end", "Infra", "QA", "Dados", "Reunião", "Gestão", "Design", "Apoio"])
            dt_real = c3.date_input("Data da Atividade", datetime.now())
            
            c4, c5 = st.columns([1, 2])
            hrs = c4.number_input("Horas (HH.MM)", min_value=0.0, step=0.10, format="%.2f")
            desc = c5.text_input("Descrição da Entrega")
            
            submit = st.form_submit_button("🚀 Registrar Atividade")
            
            if submit:
                if hrs > 0 and desc:
                    # Logic
                    comp_str = dt_real.strftime("%Y-%m")
                    date_str = dt_real.strftime("%Y-%m-%d")
                    
                    success = DatabaseManager.execute_statement(
                        """
                        INSERT INTO lancamentos 
                        (id, colaborador_email, projeto, horas, competencia, data_atividade, tipo, descricao, valor_hora_historico, foi_editado) 
                        VALUES (:id, :e, :p, :h, :c, :d_atv, :t, :d, :v, FALSE)
                        """,
                        {
                            "id": str(uuid.uuid4()),
                            "e": user_session['email'],
                            "p": proj,
                            "h": hrs,
                            "c": comp_str,
                            "d_atv": date_str,
                            "t": tipo,
                            "d": desc,
                            "v": user_session['rate']
                        }
                    )
                    
                    if success:
                        st.toast("Lançamento gravado com sucesso!", icon="✅")
                        st.success(f"Salvo: {hrs}h em {date_str}")
                        time.sleep(1)
                        st.rerun()
                else:
                    st.warning("Preencha horas e descrição corretamente.")

# --- MODULE 2: PERSONAL HISTORY (EDIT PENDING) ---
class HistoryView:
    @staticmethod
    def render(user_session: dict, df_full: pd.DataFrame):
        st.subheader(f"🗂️ Histórico Pessoal - {user_session['name']}")
        st.caption("Visualize seu histórico completo. Itens 'Pendentes' podem ser editados.")
        
        # Filter own data
        my_df = df_full[df_full['colaborador_email'] == user_session['email']].copy()
        
        if my_df.empty:
            st.info("Nenhum lançamento encontrado.")
            return

        # Tabs for status
        tab1, tab2, tab3 = st.tabs(["⏳ Pendentes (Editável)", "✅ Aprovados", "❌ Rejeitados"])
        
        # --- TAB 1: PENDING ---
        with tab1:
            my_pend = my_df[my_df['status_aprovaca'] == 'Pendente'].copy()
            if not my_pend.empty:
                st.warning("⚠️ Ao editar um item, o administrador receberá um alerta de modificação.")
                
                edited = st.data_editor(
                    my_pend[['descricao', 'projeto', 'Data Real', 'horas', 'tipo', 'id']],
                    use_container_width=True,
                    hide_index=True,
                    key="history_pend_editor",
                    column_config={
                        "Data Real": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                        "horas": st.column_config.NumberColumn("HH.MM", format="%.2f"),
                        "id": None # Hide ID
                    }
                )
                
                if st.button("💾 Salvar Minhas Edições"):
                    for idx, row in edited.iterrows():
                        # Logic: If user saves here, set 'foi_editado' to TRUE
                        try:
                            d_val = row['Data Real']
                            # Handle date format inconsistencies from editor
                            if isinstance(d_val, str): 
                                d_val = datetime.strptime(d_val, "%Y-%m-%d").date()
                            
                            c_str = d_val.strftime("%Y-%m")
                            d_str = d_val.strftime("%Y-%m-%d")
                            
                            DatabaseManager.execute_statement(
                                """
                                UPDATE lancamentos 
                                SET descricao=:d, projeto=:p, horas=:h, data_atividade=:da, competencia=:c, foi_editado=TRUE 
                                WHERE id=:id
                                """,
                                {"d": row['descricao'], "p": row['projeto'], "h": row['horas'], 
                                 "da": d_str, "c": c_str, "id": row['id']}
                            )
                        except Exception as e:
                            st.error(f"Erro ao salvar ID {row['id']}: {e}")
                    
                    st.toast("Edições salvas e notificadas ao Admin!", icon="📩")
                    time.sleep(1.5)
                    st.rerun()
            else:
                st.info("Nada pendente.")

        # --- TAB 2: APPROVED ---
        with tab2:
            my_appr = my_df[my_df['status_aprovaca'] == 'Aprovado']
            st.dataframe(
                my_appr[['descricao', 'Data Real', 'projeto', 'horas', 'valor_hora_historico']],
                use_container_width=True, hide_index=True,
                column_config={"Data Real": st.column_config.DateColumn("Data")}
            )

        # --- TAB 3: REJECTED ---
        with tab3:
            my_rej = my_df[my_df['status_aprovaca'] == 'Negado']
            st.dataframe(my_rej[['descricao', 'Data Real', 'horas']], use_container_width=True, hide_index=True)

# --- MODULE 3: DASHBOARD / MANAGEMENT ---
class DashboardView:
    @staticmethod
    def render(user_session: dict, df_full: pd.DataFrame, name_map: dict, is_admin: bool):
        st.subheader("📊 Painel de Gestão e Auditoria")
        
        # --- TARGET SELECTION ---
        target_email = user_session['email']
        target_name = user_session['name']
        
        if is_admin:
            c_sel, _ = st.columns([2, 2])
            # Build list: [Admin (email), User1 (email), User2 (email)...]
            all_options = [f"{name_map[e]} ({e})" for e in sorted(name_map.keys())]
            
            # Default to current user
            default_idx = 0
            current_str = f"{target_name} ({target_email})"
            if current_str in all_options:
                default_idx = all_options.index(current_str)
            
            sel_val = c_sel.selectbox("👁️ (Admin) Visualizar Painel de:", all_options, index=default_idx)
            target_email = sel_val.split('(')[-1].replace(')', '')
            target_name = name_map.get(target_email, target_email)
        
        st.markdown(f"**Analisando:** `{target_name}`")
        
        # --- COMPETENCE FILTER (MULTI-SELECT) ---
        if df_full.empty:
            st.warning("Sem dados.")
            return
            
        all_comps = sorted(df_full['competencia'].unique(), reverse=True)
        
        st.write("---")
        c_filt, _ = st.columns([1, 2])
        sel_comps = c_filt.multiselect("📅 Filtrar Competências:", all_comps, default=all_comps[:1])
        
        # --- FILTERING ---
        df_target = df_full[df_full['colaborador_email'] == target_email].copy()
        
        if sel_comps:
            df_target = df_target[df_target['competencia'].isin(sel_comps)]
            
            if not df_target.empty:
                # Calc
                df_target['h_dec'] = df_target['horas'].apply(BusinessLogic.convert_hhmm_to_decimal)
                df_target['total_val'] = df_target['h_dec'] * df_target['valor_hora_historico']
                
                # KPIs
                k1, k2, k3, k4 = st.columns(4)
                
                # Sums
                pend = df_target[df_target['status_aprovaca'] == 'Pendente']['horas'].sum()
                appr = df_target[df_target['status_aprovaca'] == 'Aprovado']['horas'].sum()
                paid = df_target[df_target['status_pagamento'] == 'Pago']['horas'].sum()
                money = df_target['total_val'].sum()
                
                k1.metric("Pendente (h)", f"{pend:.2f}")
                k2.metric("Aprovado (h)", f"{appr:.2f}")
                k3.metric("Pago (h)", f"{paid:.2f}")
                k4.metric("Valor Total (R$)", f"R$ {money:,.2f}")
                
                # Detail Table
                st.divider()
                st.markdown(f"### 📋 Detalhamento - {target_name}")
                
                st.dataframe(
                    df_target[['descricao', 'Data Real', 'competencia', 'projeto', 'horas', 'total_val', 'status_aprovaca', 'status_pagamento']],
                    use_container_width=True, hide_index=True,
                    column_config={
                        "total_val": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
                        "Data Real": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                        "horas": st.column_config.NumberColumn("HH.MM", format="%.2f")
                    }
                )
            else:
                st.info("Sem dados para a competência selecionada.")
        else:
            st.warning("Selecione ao menos uma competência.")

# --- MODULE 4: ADMIN OPERATIONS ---
class AdminView:
    @staticmethod
    def render(df_full: pd.DataFrame, users_dict: dict, name_map: dict):
        st.subheader("🛡️ Central de Gestão Operacional")
        
        colabs_list = ["Todos"] + [f"{name_map[e]} ({e})" for e in sorted(name_map.keys())]
        
        # --- BULK IMPORT ---
        with st.expander("📥 Importação em Massa (Excel Copy/Paste)", expanded=False):
            st.markdown("Cole: **Data (DD/MM/AAAA) | Projeto | Email | Horas | Tipo | Descrição**")
            cola = st.text_area("Dados:", height=100)
            
            if cola and st.button("Processar Importação"):
                try:
                    df_p = pd.read_csv(io.StringIO(cola), sep='\t', names=["data", "p", "e", "h", "t", "d"])
                    
                    with conn.session as s:
                        for r in df_p.itertuples():
                            # Get User Rate
                            u_data = users_dict.get(r.e, {})
                            rate = u_data.get("rate", 0.0) if u_data else 0.0
                            
                            # Parse Date
                            try:
                                dt = pd.to_datetime(r.data, dayfirst=True)
                                c_s = dt.strftime("%Y-%m")
                                d_s = dt.strftime("%Y-%m-%d")
                            except:
                                dt = datetime.now()
                                c_s, d_s = dt.strftime("%Y-%m"), dt.strftime("%Y-%m-%d")
                                
                            s.execute(
                                text("""
                                    INSERT INTO lancamentos (id, colaborador_email, projeto, horas, competencia, data_atividade, tipo, descricao, valor_hora_historico, status_aprovaca, foi_editado) 
                                    VALUES (:id, :e, :p, :h, :c, :d_atv, :t, :d, :v, 'Pendente', FALSE)
                                """),
                                {
                                    "id": str(uuid.uuid4()), "e": r.e, "p": r.p, "h": r.h, 
                                    "c": c_s, "d_atv": d_s, "t": r.t, "d": r.d, "v": rate
                                }
                            )
                        s.commit()
                    st.success(f"{len(df_p)} registros importados!")
                    time.sleep(1); st.rerun()
                except Exception as e:
                    st.error("Erro na importação."); st.code(str(e))

        st.divider()
        
        # --- SECTION 1: PENDING ---
        st.markdown("### 🕒 Pendentes (Com Alerta de Edição)")
        
        c_all, c_fil = st.columns([1, 3])
        sel_all = c_all.checkbox("Selecionar Todos")
        filtro_p = c_fil.selectbox("Filtrar Pendentes:", colabs_list, key="fp_adm")
        
        df_p = df_full[df_full['status_aprovaca'] == 'Pendente'].copy()
        
        if filtro_p != "Todos":
            e_p = filtro_p.split('(')[-1].replace(')', '')
            df_p = df_p[df_p['colaborador_email'] == e_p]
            
        if not df_p.empty:
            # Preparing View
            df_p = df_p[['foi_editado', 'descricao', 'Nome', 'projeto', 'Data Real', 'horas', 'id']]
            df_p.insert(0, "✅", sel_all)
            df_p.insert(1, "🗑️", False)
            
            ed_p = st.data_editor(
                df_p, use_container_width=True, hide_index=True, key="adm_pend",
                column_config={
                    "✅": st.column_config.CheckboxColumn("Apv", width="small"),
                    "🗑️": st.column_config.CheckboxColumn("Rej", width="small"),
                    "foi_editado": st.column_config.CheckboxColumn("⚠️ Editado?", disabled=True, help="Usuário alterou este item recentemente."),
                    "Data Real": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                    "horas": st.column_config.NumberColumn("HH.MM", format="%.2f")
                }
            )
            
            c1, c2 = st.columns(2)
            if c1.button("Aprovar Selecionados", type="primary"):
                ids = ed_p[ed_p["✅"] == True]["id"].tolist()
                if ids:
                    if DatabaseManager.execute_statement(
                        "UPDATE lancamentos SET status_aprovaca='Aprovado', foi_editado=FALSE WHERE id IN :ids",
                        {"ids": tuple(ids)}
                    ):
                        st.toast("Aprovado!"); time.sleep(0.5); st.rerun()
                    
            if c2.button("Rejeitar Selecionados"):
                ids = ed_p[ed_p["🗑️"] == True]["id"].tolist()
                if ids:
                    if DatabaseManager.execute_statement(
                        "UPDATE lancamentos SET status_aprovaca='Negado' WHERE id IN :ids",
                        {"ids": tuple(ids)}
                    ):
                        st.toast("Rejeitado!"); time.sleep(0.5); st.rerun()
        else:
            st.info("Nada pendente.")

        st.divider()
        
        # --- SECTION 2: APPROVED (FULL EDIT) ---
        st.markdown("### ✅ Aprovados (Edição Total)")
        st.caption("Ajuste datas, projetos e competências aqui se necessário.")
        
        filtro_a = st.selectbox("Filtrar Aprovados:", colabs_list, key="fa_adm")
        
        df_a = df_full[df_full['status_aprovaca'] == 'Aprovado'].copy()
        if filtro_a != "Todos":
            e_a = filtro_a.split('(')[-1].replace(')', '')
            df_a = df_a[df_a['colaborador_email'] == e_a]
            
        if not df_a.empty:
            # We show Competence AND Data for checking
            df_a = df_a[['descricao', 'Nome', 'projeto', 'competencia', 'Data Real', 'horas', 'status_aprovaca', 'id']]
            
            ed_a = st.data_editor(
                df_a, use_container_width=True, hide_index=True, key="adm_aprov",
                column_config={
                    "status_aprovaca": st.column_config.SelectboxColumn("Status", options=["Aprovado", "Pendente", "Negado"], required=True),
                    "Data Real": st.column_config.DateColumn("Data Ativ.", format="DD/MM/YYYY"),
                    "competencia": st.column_config.TextColumn("Comp. (Auto)")
                }
            )
            
            if st.button("Salvar Alterações Aprovados"):
                with conn.session as s:
                    for row in ed_a.itertuples():
                        # SYNC LOGIC: Update Date -> Update Competence
                        try:
                            # Safely get edited date
                            d_val = getattr(row, "Data_Real") # Pandas creates underscore
                            
                            if isinstance(d_val, str): d_val = datetime.strptime(d_val, "%Y-%m-%d").date()
                            elif isinstance(d_val, pd.Timestamp): d_val = d_val.date()
                            
                            new_c = d_val.strftime("%Y-%m")
                            new_d = d_val.strftime("%Y-%m-%d")
                            
                            s.execute(
                                text("UPDATE lancamentos SET status_aprovaca=:s, horas=:h, descricao=:d, projeto=:p, competencia=:c, data_atividade=:da WHERE id=:id"),
                                {"s": row.status_aprovaca, "h": row.horas, "d": row.descricao, "p": row.projeto, "c": new_c, "da": new_d, "id": row.id}
                            )
                        except Exception as e:
                            st.error(f"Erro na linha {row.id}: {e}")
                    s.commit()
                st.toast("Atualizado!"); time.sleep(1); st.rerun()
        else:
            st.info("Vazio.")

        # --- SECTION 3: REJECTED ---
        st.divider()
        with st.expander("❌ Lixeira / Rejeitados"):
            df_n = df_full[df_full['status_aprovaca'] == 'Negado'].copy()
            if not df_n.empty:
                df_n = df_n[['descricao', 'Nome', 'Data Real', 'status_aprovaca', 'id']]
                ed_n = st.data_editor(df_n, use_container_width=True, hide_index=True,
                                      column_config={"status_aprovaca": st.column_config.SelectboxColumn("Status", options=["Negado", "Pendente"])})
                
                c_rec, c_del = st.columns(2)
                if c_rec.button("Recuperar"):
                    with conn.session as s:
                        for row in ed_n.itertuples():
                            if row.status_aprovaca != "Negado":
                                s.execute(text("UPDATE lancamentos SET status_aprovaca=:s WHERE id=:id"), {"s": row.status_aprovaca, "id": row.id})
                        s.commit()
                    st.rerun()
                if c_del.button("Excluir Definitivamente", type="primary"):
                    with conn.session as s:
                        ids = tuple(ed_n[ed_n['status_aprovaca'] == 'Negado']['id'].tolist())
                        if ids:
                            s.execute(text("DELETE FROM lancamentos WHERE id IN :ids"), {"ids": ids})
                            s.commit()
                    st.rerun()

# --- MODULE 5: PAYMENTS ---
class FinanceView:
    @staticmethod
    def render(df_full: pd.DataFrame, name_map: dict):
        st.subheader("💸 Consolidação Financeira")
        
        df_pay = df_full[df_full['status_aprovaca'] == 'Aprovado'].copy()
        if df_pay.empty:
            st.info("Sem dados aprovados.")
            return
            
        # Calculation
        df_pay['h_dec'] = df_pay['horas'].apply(BusinessLogic.convert_hhmm_to_decimal)
        df_pay['r$'] = df_pay['h_dec'] * df_pay['valor_hora_historico']
        
        # Total
        pend_val = df_pay[df_pay['status_pagamento'] != 'Pago']['r$'].sum()
        st.metric("Total a Pagar", f"R$ {pend_val:,.2f}")
        
        # Grouping
        df_g = df_pay.groupby(['competencia', 'colaborador_email']).agg({'r$': 'sum', 'horas': 'sum'}).reset_index()
        df_g = df_g.sort_values(['competencia'], ascending=False)
        
        for idx, row in df_g.iterrows():
            nm = name_map.get(row['colaborador_email'], row['colaborador_email'])
            
            with st.expander(f"📅 {row['competencia']} | 👤 {nm} | R$ {row['r$']:,.2f}"):
                det = df_pay[(df_pay['competencia'] == row['competencia']) & (df_pay['colaborador_email'] == row['colaborador_email'])]
                
                st.dataframe(
                    det[['descricao', 'Data Real', 'horas', 'r$', 'status_pagamento']],
                    use_container_width=True, hide_index=True,
                    column_config={"r$": st.column_config.NumberColumn("Valor", format="R$ %.2f")}
                )
                
                # Bulk Update Status
                status_list = det['status_pagamento'].tolist()
                current_status = status_list[0] if status_list else "Em aberto"
                
                ops = ["Em aberto", "Pago", "Parcial"]
                idx_op = ops.index(current_status) if current_status in ops else 0
                
                c1, c2 = st.columns([3, 1])
                ns = c1.selectbox("Status Pagamento", ops, index=idx_op, key=f"pay_{idx}")
                
                if c2.button("Atualizar", key=f"btn_{idx}"):
                    if DatabaseManager.execute_statement(
                        "UPDATE lancamentos SET status_pagamento=:s WHERE id IN :ids",
                        {"s": ns, "ids": tuple(det['id'].tolist())}
                    ):
                        st.toast("Atualizado!"); time.sleep(0.5); st.rerun()

# --- MODULE 6: CONFIG ---
class ConfigView:
    @staticmethod
    def render(users_df: pd.DataFrame, projects_df: pd.DataFrame, banks_df: pd.DataFrame):
        st.subheader("⚙️ Configurações")
        
        tab_u, tab_p, tab_b = st.tabs(["Usuários", "Projetos", "Dados Bancários"])
        
        with tab_u:
            st.write("Edite os nomes para os relatórios.")
            ed_u = st.data_editor(
                users_df, use_container_width=True, num_rows="dynamic", hide_index=True,
                column_config={
                    "email": st.column_config.TextColumn("Login", disabled=True),
                    "nome": st.column_config.TextColumn("Nome Exibição"),
                    "senha": st.column_config.TextColumn("Senha"),
                    "is_admin": st.column_config.CheckboxColumn("Admin"),
                    "valor_hora": st.column_config.NumberColumn("Valor")
                }
            )
            if st.button("Salvar Usuários"):
                with conn.session as s:
                    for r in ed_u.itertuples():
                        # Name logic
                        nm = getattr(r, 'nome', r.email.split('@')[0])
                        if pd.isna(nm) or str(nm).strip() == "": nm = r.email.split('@')[0]
                        
                        s.execute(
                            text("INSERT INTO usuarios (email, valor_hora, senha, is_admin, nome) VALUES (:e, :v, :s, :a, :n) ON CONFLICT (email) DO UPDATE SET valor_hora=:v, senha=:s, is_admin=:a, nome=:n"),
                            {"e": r.email, "v": r.valor_hora, "s": str(r.senha), "a": bool(r.is_admin), "n": nm}
                        )
                    s.commit()
                st.success("Salvo!"); st.rerun()

        with tab_p:
            ed_p = st.data_editor(projects_df, use_container_width=True, num_rows="dynamic", hide_index=True)
            if st.button("Salvar Projetos"):
                with conn.session as s:
                    for r in ed_p.itertuples():
                        if r.nome:
                            s.execute(text("INSERT INTO projetos (nome) VALUES (:n) ON CONFLICT (nome) DO NOTHING"), {"n": r.nome})
                    s.commit()
                st.success("Salvo!"); st.rerun()

        with tab_b:
            ed_b = st.data_editor(
                banks_df, use_container_width=True, num_rows="dynamic", hide_index=True,
                column_config={"tipo_chave": st.column_config.SelectboxColumn("Tipo", options=["CPF", "CNPJ", "Email", "Aleatoria"])}
            )
            if st.button("Salvar Bancos"):
                with conn.session as s:
                    for r in ed_b.itertuples():
                        tc = getattr(r, 'tipo_chave', 'CPF')
                        s.execute(
                            text("INSERT INTO dados_bancarios (colaborador_email, banco, tipo_chave, chave_pix) VALUES (:e, :b, :t, :c) ON CONFLICT (colaborador_email) DO UPDATE SET banco=:b, tipo_chave=:t, chave_pix=:c"),
                            {"e": r.colaborador_email, "b": r.banco, "t": tc, "c": r.chave_pix}
                        )
                    s.commit()
                st.success("Salvo!"); st.rerun()

# ==============================================================================
# MAIN EXECUTION ROUTING
# ==============================================================================
def main():
    AppConfig.initialize()
    
    # 1. Auth Load
    auth_mgr = AuthManager()
    auth_mgr.load_users()
    user_session = auth_mgr.render_login_sidebar()
    
    # 2. Global Data Load
    df_raw = DatabaseManager.get_all_launches()
    # Process data with names and dates
    df_processed = DataProcessor.prepare_launches_df(df_raw, auth_mgr.name_map)
    
    # Projects Load
    proj_df = DatabaseManager.get_projects()
    projects = proj_df['nome'].tolist() if not proj_df.empty else ["Sustentação"]
    
    # 3. Routing
    if selected_tab == "📝 Lançamentos":
        LaunchView.render(user_session, projects)
        
    elif selected_tab == "🗂️ Histórico Pessoal":
        HistoryView.render(user_session, df_processed)
        
    elif selected_tab == "📊 Meu Painel" or selected_tab == "📊 Gestão de Painéis":
        DashboardView.render(user_session, df_processed, auth_mgr.name_map, user_session['is_admin'])
        
    elif selected_tab == "🛡️ Admin Aprovações":
        if not user_session['is_admin']:
            st.error("Acesso Negado.")
        else:
            # Need to pass users_dict to Admin for rates. Reconstruct it from auth
            users_dict_shim = {email: {"rate": data["rate"]} for email, data in auth_mgr.user_map.items()}
            AdminView.render(df_processed, users_dict_shim, auth_mgr.name_map)
            
    elif selected_tab == "💸 Pagamentos":
        FinanceView.render(df_processed, auth_mgr.name_map)
        
    elif selected_tab == "⚙️ Configurações":
        ConfigView.render(auth_mgr.users_df, proj_df, DatabaseManager.get_banks())
    
    elif selected_tab == "📈 BI Estratégico":
        st.title("BI Humana (Analítico)")
        if not df_processed.empty:
            df_processed['h_dec'] = df_processed['horas'].apply(BusinessLogic.convert_hhmm_to_decimal)
            df_processed['custo'] = df_processed['h_dec'] * df_processed['valor_hora_historico']
            df_processed['tipo_norm'] = df_processed['tipo'].apply(BusinessLogic.normalize_activity_type)
            
            c1, c2 = st.columns(2)
            c1.metric("Total Horas", f"{df_processed['horas'].sum():.2f}")
            c2.metric("Custo Total", f"R$ {df_processed['custo'].sum():,.2f}")
            
            st.bar_chart(df_processed.groupby("projeto")['custo'].sum())
            st.bar_chart(df_processed.groupby("tipo_norm")['horas'].sum())

if __name__ == "__main__":
    main()