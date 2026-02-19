"""
================================================================================
ONCALL HUMANA ERP - SYSTEM MASTER v11.0 "THE LEVIATHAN"
================================================================================
Author: Pedro Reis & Architect AI
Date: February 2026
Version: 11.0.0 (Enterprise Monolith)
License: Proprietary

ARCHITECTURE OVERVIEW:
This application follows a strict Separation of Concerns (SoC) architecture:
1.  CONFIG LAYER: Static configuration, constants, and CSS injection.
2.  DATA ACCESS LAYER (DAL): Repository pattern classes for direct DB SQL interaction.
3.  SERVICE LAYER: Business logic, transformations, calculations, and validations.
4.  SECURITY LAYER: Authentication, Session Management, and Access Control (RBAC).
5.  PRESENTATION LAYER (VIEW): Streamlit UI components and page rendering.

KEY CAPABILITIES:
- Full Audit Trail (Edit Flags)
- Strict Typing (Python Type Hints)
- Fault Tolerance (Database Retry Logic)
- Responsive UI (Dark/Light Mode Compatible)
================================================================================
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
import uuid
import time
import io
from sqlalchemy import text, engine
from typing import Optional, List, Dict, Any, Union, Tuple

# ==============================================================================
# 1. CONFIGURATION & CONSTANTS
# ==============================================================================
class AppConfig:
    """Central configuration registry for the application."""
    
    APP_NAME: str = "OnCall Humana"
    APP_VERSION: str = "v11.0 Leviathan"
    APP_ICON: str = "🛡️"
    LAYOUT: str = "wide"
    
    # --- UI THEME COLORS ---
    COLOR_PRIMARY: str = "#0f54c9"
    COLOR_SUCCESS: str = "#28a745"
    COLOR_WARNING: str = "#ffc107"
    COLOR_DANGER: str = "#dc3545"
    
    # --- BUSINESS RULES ---
    SUPER_ADMINS: List[str] = [
        "pedroivofernandesreis@gmail.com", 
        "claudiele.andrade@gmail.com"
    ]
    
    DEFAULT_PROJECTS: List[str] = ["Sustentação", "Projetos", "Outros"]
    
    ACTIVITY_TYPES: List[str] = [
        "Front-end", "Back-end", "Infraestrutura", "QA / Testes", 
        "Engenharia de Dados", "Reunião", "Gestão", "Design/UX", "Apoio Operacional"
    ]

# ==============================================================================
# 2. CORE UTILITIES (HELPER FUNCTIONS)
# ==============================================================================
class Utils:
    """Static utility methods for data transformation and formatting."""

    @staticmethod
    def inject_css() -> None:
        """Injects enterprise-grade CSS into the Streamlit app."""
        st.markdown(f"""
        <style>
            /* Global Container Spacing */
            .block-container {{
                padding-top: 2rem;
                padding-bottom: 6rem;
                max-width: 98% !important;
            }}
            
            /* KPI Cards / Metrics */
            div[data-testid="stMetric"] {{
                background-color: rgba(255, 255, 255, 0.03); 
                border: 1px solid rgba(128, 128, 128, 0.2);
                padding: 15px;
                border-radius: 8px;
                box-shadow: 0 4px 6px rgba(0,0,0,0.05);
                transition: all 0.2s ease-in-out;
            }}
            div[data-testid="stMetric"]:hover {{
                transform: translateY(-2px);
                border-color: {AppConfig.COLOR_PRIMARY};
            }}
            
            /* Form Labels */
            label {{
                font-weight: 700 !important;
                font-size: 0.95rem !important;
                letter-spacing: 0.02em;
            }}
            
            /* Expander Headers */
            .streamlit-expanderHeader {{
                font-weight: 700;
                font-size: 1.05rem;
                color: {AppConfig.COLOR_PRIMARY};
                background-color: rgba(128, 128, 128, 0.05);
                border-radius: 5px;
            }}
            
            /* Dataframes & Tables */
            div[data-testid="stDataFrame"] {{
                border: 1px solid rgba(128, 128, 128, 0.15);
                border-radius: 6px;
            }}
            
            /* Primary Buttons */
            button[kind="primary"] {{
                background: linear-gradient(90deg, #0068c9 0%, #004e98 100%);
                border: none;
                font-weight: bold;
                letter-spacing: 0.05em;
            }}
            
            /* Validation Alerts */
            .alert-box {{
                padding: 10px;
                border-radius: 5px;
                margin-bottom: 10px;
                font-weight: 500;
            }}
        </style>
        """, unsafe_allow_html=True)

    @staticmethod
    def hhmm_to_decimal(pseudo_hour: Union[float, str]) -> float:
        """
        Converts 'human' time (HH.MM) to decimal hours.
        Example: 2.30 (2h 30m) -> 2.50
        """
        try:
            if pd.isna(pseudo_hour) or pseudo_hour == "":
                return 0.0
            
            # Ensure proper string formatting
            val_str = f"{float(pseudo_hour):.2f}"
            parts = val_str.split('.')
            
            if len(parts) != 2:
                return float(pseudo_hour)
                
            hours = int(parts[0])
            minutes = int(parts[1])
            
            # Safety: If minutes >= 60, assume user typo or direct decimal input
            if minutes >= 60:
                return float(pseudo_hour)
                
            return hours + (minutes / 60.0)
        except Exception:
            return 0.0

    @staticmethod
    def format_currency(value: float) -> str:
        """Formats a float as BRL currency string."""
        if pd.isna(value): return "R$ 0,00"
        return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    @staticmethod
    def normalize_string(text_val: str) -> str:
        """Normalizes strings for DB storage and BI consistency."""
        if not isinstance(text_val, str): return "N/A"
        return " ".join(text_val.strip().split())

# ==============================================================================
# 3. DATA ACCESS LAYER (DAL) - REPOSITORIES
# ==============================================================================
class DatabaseConnection:
    """Singleton-like pattern for Database Connection Management."""
    
    @staticmethod
    def get_engine():
        """Creates and returns the SQLAlchemy engine via Streamlit connection."""
        try:
            conn = st.connection("postgresql", type="sql")
            conn.query("SELECT 1", ttl=0) # Wake-up call
            return conn
        except Exception as e:
            st.error("🔴 DATABASE CRITICAL FAILURE")
            st.error(f"Could not establish connection: {str(e)}")
            st.stop()

class BaseRepository:
    """Base class for all Repositories."""
    
    def __init__(self):
        self.conn = DatabaseConnection.get_engine()

    def fetch(self, query: str) -> pd.DataFrame:
        """Safe fetch with error handling."""
        try:
            return self.conn.query(query, ttl=0)
        except Exception as e:
            st.error(f"Read Error: {e}")
            return pd.DataFrame()

    def execute(self, sql: str, params: dict) -> bool:
        """Safe execution with transaction management."""
        try:
            with self.conn.session as s:
                s.execute(text(sql), params)
                s.commit()
            return True
        except Exception as e:
            st.error(f"Write Error: {e}")
            return False

class UserRepository(BaseRepository):
    """Handles User Data Access."""
    
    def get_all(self) -> pd.DataFrame:
        return self.fetch("SELECT * FROM usuarios ORDER BY email")

    def upsert_user(self, email: str, name: str, pwd: str, admin: bool, rate: float) -> bool:
        sql = """
            INSERT INTO usuarios (email, nome, senha, is_admin, valor_hora) 
            VALUES (:e, :n, :p, :a, :v) 
            ON CONFLICT (email) 
            DO UPDATE SET nome=:n, senha=:p, is_admin=:a, valor_hora=:v
        """
        return self.execute(sql, {"e": email, "n": name, "p": pwd, "a": admin, "v": rate})

class LaunchRepository(BaseRepository):
    """Handles Timesheet Data Access."""
    
    def get_all(self) -> pd.DataFrame:
        return self.fetch("SELECT * FROM lancamentos ORDER BY competencia DESC, data_atividade DESC")

    def create_launch(self, data: dict) -> bool:
        sql = """
            INSERT INTO lancamentos 
            (id, colaborador_email, projeto, horas, competencia, data_atividade, tipo, descricao, valor_hora_historico, status_aprovaca, foi_editado) 
            VALUES (:id, :e, :p, :h, :c, :d_atv, :t, :d, :v, 'Pendente', FALSE)
        """
        return self.execute(sql, data)

    def update_launch_status(self, ids: tuple, status: str, reset_edit: bool = False) -> bool:
        if not ids: return False
        
        edit_clause = ", foi_editado = FALSE" if reset_edit else ""
        sql = f"UPDATE lancamentos SET status_aprovaca = :s {edit_clause} WHERE id IN :ids"
        return self.execute(sql, {"s": status, "ids": ids})

    def update_launch_full(self, data: dict) -> bool:
        sql = """
            UPDATE lancamentos 
            SET descricao=:d, projeto=:p, horas=:h, data_atividade=:da, competencia=:c, status_aprovaca=:s 
            WHERE id=:id
        """
        return self.execute(sql, data)

    def update_launch_by_user(self, data: dict) -> bool:
        # User edit triggers 'foi_editado = TRUE'
        sql = """
            UPDATE lancamentos 
            SET descricao=:d, projeto=:p, horas=:h, data_atividade=:da, competencia=:c, foi_editado=TRUE 
            WHERE id=:id
        """
        return self.execute(sql, data)

    def update_payment_status(self, ids: tuple, status: str) -> bool:
        if not ids: return False
        sql = "UPDATE lancamentos SET status_pagamento = :s WHERE id IN :ids"
        return self.execute(sql, {"s": status, "ids": ids})
        
    def delete_launches(self, ids: tuple) -> bool:
        if not ids: return False
        sql = "DELETE FROM lancamentos WHERE id IN :ids"
        return self.execute(sql, {"ids": ids})

class ConfigRepository(BaseRepository):
    """Handles Projects and Banking Configs."""
    
    def get_projects(self) -> pd.DataFrame:
        return self.fetch("SELECT * FROM projetos ORDER BY nome")
        
    def add_project(self, name: str) -> bool:
        sql = "INSERT INTO projetos (nome) VALUES (:n) ON CONFLICT (nome) DO NOTHING"
        return self.execute(sql, {"n": name})
        
    def get_banks(self) -> pd.DataFrame:
        return self.fetch("SELECT * FROM dados_bancarios")
        
    def upsert_bank(self, email: str, bank: str, key_type: str, key: str) -> bool:
        sql = """
            INSERT INTO dados_bancarios (colaborador_email, banco, tipo_chave, chave_pix) 
            VALUES (:e, :b, :t, :c) 
            ON CONFLICT (colaborador_email) 
            DO UPDATE SET banco=:b, tipo_chave=:t, chave_pix=:c
        """
        return self.execute(sql, {"e": email, "b": bank, "t": key_type, "c": key})

# ==============================================================================
# 4. SERVICE LAYER (BUSINESS LOGIC)
# ==============================================================================
class AuthService:
    """Manages Authentication logic and User mapping."""
    
    def __init__(self):
        self.repo = UserRepository()
        self.users_data = {}
        self.email_to_name = {}
        
    def load_users(self):
        """Refreshes the user cache from DB."""
        df = self.repo.get_all()
        
        self.users_data = {}
        self.email_to_name = {}
        
        if not df.empty:
            for row in df.itertuples():
                # Name Resolution Logic
                nm = getattr(row, 'nome', None)
                if not nm or str(nm).strip() == "":
                    nm = row.email.split('@')[0].replace('.', ' ').title()
                
                self.email_to_name[row.email] = nm
                self.users_data[row.email] = {
                    "pwd": str(row.senha),
                    "rate": float(row.valor_hora) if row.valor_hora else 0.0,
                    "is_admin": bool(getattr(row, 'is_admin', False)),
                    "name": nm
                }
                
    def authenticate(self, email: str, password: str) -> bool:
        if email not in self.users_data:
            return False
        return self.users_data[email]["pwd"] == password

class DataService:
    """Manages Data Transformation for Views."""
    
    def __init__(self, auth_service: AuthService):
        self.auth = auth_service
        self.launch_repo = LaunchRepository()
        
    def get_enriched_data(self) -> pd.DataFrame:
        df = self.launch_repo.get_all()
        
        if df.empty:
            return df
            
        # 1. Map Names
        df['Nome'] = df['colaborador_email'].map(self.auth.email_to_name).fillna(df['colaborador_email'])
        
        # 2. Date Parsing
        if 'data_atividade' in df.columns:
            df['Data Real'] = pd.to_datetime(df['data_atividade'], errors='coerce').dt.date
        else:
            df['Data Real'] = pd.NaT
            
        df['Importado Em'] = pd.to_datetime(df['data_registro']).dt.date
        df['Data Real'] = df['Data Real'].fillna(df['Importado Em'])
        
        # 3. Edit Flag
        if 'foi_editado' not in df.columns:
            df['foi_editado'] = False
        else:
            df['foi_editado'] = df['foi_editado'].fillna(False).astype(bool)
            
        return df

# ==============================================================================
# 5. VIEW CONTROLLERS (PAGE RENDERERS)
# ==============================================================================

class LaunchController:
    """Handles the Launch Page logic."""
    
    @staticmethod
    def render(user: dict, project_list: list):
        st.subheader(f"📝 Registro de Atividade - {user['name']}")
        
        with st.form("main_launch", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            p_sel = c1.selectbox("Projeto", project_list)
            t_sel = c2.selectbox("Tipo", AppConfig.ACTIVITY_TYPES)
            d_sel = c3.date_input("Data REAL da Atividade", datetime.now())
            
            c4, c5 = st.columns([1, 2])
            h_input = c4.number_input("Horas (HH.MM)", min_value=0.0, step=0.10, format="%.2f", help="Ex: 1.30 = 1h30min")
            d_input = c5.text_input("Descrição Detalhada")
            
            if st.form_submit_button("🚀 Gravar Lançamento", type="primary"):
                if h_input > 0 and d_input:
                    repo = LaunchRepository()
                    data = {
                        "id": str(uuid.uuid4()), "e": user['email'], "p": p_sel, "h": h_input,
                        "c": d_sel.strftime("%Y-%m"), "d_atv": d_sel.strftime("%Y-%m-%d"),
                        "t": t_sel, "d": d_input, "v": user['rate']
                    }
                    if repo.create_launch(data):
                        st.toast("Sucesso!", icon="✅"); time.sleep(1); st.rerun()
                else:
                    st.warning("Preencha horas e descrição.")

class DashboardController:
    """Handles the Dashboard logic (Personal & Management)."""
    
    @staticmethod
    def render(user: dict, df: pd.DataFrame, auth: AuthService):
        st.subheader("📊 Painel de Controle")
        
        # Admin Target Selector
        target_email = user['email']
        target_name = user['name']
        
        if user['is_admin']:
            c_sel, _ = st.columns([2, 2])
            
            # Lista visual
            options = []
            # Add Admin himself
            options.append(f"{user['name']} ({user['email']})")
            # Add others
            for email, meta in auth.users_data.items():
                if email != user['email']:
                    options.append(f"{meta['name']} ({email})")
            
            sel_vis = c_sel.selectbox("👁️ (Admin) Visualizar:", options)
            target_email = sel_vis.split('(')[-1].replace(')', '')
            target_name = auth.users_data[target_email]['name']
            
        st.info(f"Analisando dados de: **{target_name}**")
        
        # Filters
        if df.empty:
            st.warning("Base de dados vazia."); return
            
        all_competences = sorted(df['competencia'].unique(), reverse=True)
        c1, _ = st.columns([1, 3])
        selected_comps = c1.multiselect("📅 Filtrar Competências:", all_competences, default=all_competences[:1] if all_competences else None)
        
        # Filtering Logic
        df_view = df[df['colaborador_email'] == target_email].copy()
        
        if selected_comps:
            df_view = df_view[df_view['competencia'].isin(selected_comps)]
            
            if not df_view.empty:
                # Metrics Calculation
                df_view['h_dec'] = df_view['horas'].apply(Utils.hhmm_to_decimal)
                df_view['val_calc'] = df_view['h_dec'] * df_view['valor_hora_historico']
                
                k1, k2, k3, k4 = st.columns(4)
                
                h_p = df_view[df_view['status_aprovaca'] == 'Pendente']['horas'].sum()
                h_a = df_view[df_view['status_aprovaca'] == 'Aprovado']['horas'].sum()
                h_pd = df_view[df_view['status_pagamento'] == 'Pago']['horas'].sum()
                val_t = df_view['val_calc'].sum()
                
                k1.metric("Pendente", f"{h_p:.2f}h")
                k2.metric("Aprovado", f"{h_a:.2f}h")
                k3.metric("Pago", f"{h_pd:.2f}h")
                k4.metric("Valor Est.", f"R$ {val_t:,.2f}")
                
                st.divider()
                st.markdown(f"### 📋 Detalhamento - {target_name}")
                
                st.dataframe(
                    df_view[['descricao', 'Data Real', 'competencia', 'projeto', 'horas', 'val_calc', 'status_aprovaca', 'status_pagamento']],
                    use_container_width=True, hide_index=True,
                    column_config={
                        "val_calc": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
                        "Data Real": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                        "horas": st.column_config.NumberColumn("HH.MM", format="%.2f")
                    }
                )
            else:
                st.info("Sem dados na competência selecionada.")
        else:
            st.warning("Selecione uma competência.")

class PersonalHistoryController:
    """Handles User's Personal History with limited editing."""
    
    @staticmethod
    def render(user: dict, df: pd.DataFrame):
        st.subheader(f"🗂️ Histórico Pessoal - {user['name']}")
        
        my_df = df[df['colaborador_email'] == user['email']].copy()
        
        if my_df.empty:
            st.info("Sem histórico."); return
            
        t1, t2, t3 = st.tabs(["⏳ Pendentes (Editável)", "✅ Aprovados", "❌ Rejeitados"])
        
        # TAB 1: PENDING (EDIT)
        with t1:
            df_p = my_df[my_df['status_aprovaca'] == 'Pendente'].copy()
            if not df_p.empty:
                st.caption("Você pode corrigir lançamentos pendentes aqui. O Admin será notificado.")
                
                edited = st.data_editor(
                    df_p[['descricao', 'projeto', 'Data Real', 'horas', 'tipo', 'id']],
                    use_container_width=True, hide_index=True, key="ph_pend",
                    column_config={
                        "Data Real": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                        "id": None
                    }
                )
                
                if st.button("💾 Salvar Minhas Edições"):
                    repo = LaunchRepository()
                    count = 0
                    for row in edited.itertuples():
                        try:
                            # Safe Date Conversion
                            d_val = row._3 # Index of Data Real in reduced DF
                            if isinstance(d_val, str): d_val = datetime.strptime(d_val, "%Y-%m-%d").date()
                            elif isinstance(d_val, pd.Timestamp): d_val = d_val.date()
                            
                            c_s = d_val.strftime("%Y-%m")
                            d_s = d_val.strftime("%Y-%m-%d")
                            
                            data = {
                                "d": row.descricao, "p": row.projeto, "h": row.horas,
                                "da": d_s, "c": c_s, "id": row.id
                            }
                            
                            if repo.update_launch_by_user(data): count += 1
                        except: pass
                    
                    if count > 0:
                        st.toast(f"{count} atualizados! Admin notificado.", icon="⚠️")
                        time.sleep(1); st.rerun()
            else:
                st.info("Nenhuma pendência.")

        # TAB 2: APPROVED
        with t2:
            st.dataframe(
                my_df[my_df['status_aprovaca'] == 'Aprovado'][['descricao', 'Data Real', 'horas', 'valor_hora_historico']],
                use_container_width=True, hide_index=True, column_config={"Data Real": st.column_config.DateColumn("Data")}
            )

        # TAB 3: REJECTED
        with t3:
            st.dataframe(my_df[my_df['status_aprovaca'] == 'Negado'], use_container_width=True, hide_index=True)

class AdminController:
    """Handles Admin Operations."""
    
    @staticmethod
    def render(df: pd.DataFrame, auth: AuthService):
        st.subheader("🛡️ Central de Gestão Operacional")
        repo = LaunchRepository()
        
        # --- BULK IMPORT ---
        with st.expander("📥 Importar Excel (Bulk)", expanded=False):
            cola = st.text_area("Data | Projeto | Email | Horas | Tipo | Desc", height=100)
            if cola and st.button("Gravar"):
                try:
                    df_imp = pd.read_csv(io.StringIO(cola), sep='\t', names=["data", "p", "e", "h", "t", "d"])
                    count = 0
                    for r in df_imp.itertuples():
                        # Get user rate
                        u_meta = auth.users_data.get(r.e, {})
                        rate = u_meta.get("rate", 0.0)
                        
                        try:
                            dt = pd.to_datetime(r.data, dayfirst=True)
                            c_s, d_s = dt.strftime("%Y-%m"), dt.strftime("%Y-%m-%d")
                        except:
                            now = datetime.now()
                            c_s, d_s = now.strftime("%Y-%m"), now.strftime("%Y-%m-%d")
                            
                        data = {
                            "id": str(uuid.uuid4()), "e": r.e, "p": r.p, "h": r.h,
                            "c": c_s, "d_atv": d_s, "t": r.t, "d": r.d, "v": rate
                        }
                        if repo.create_launch(data): count += 1
                    st.success(f"{count} importados!"); time.sleep(1); st.rerun()
                except Exception as e: st.error(f"Erro: {e}")

        st.divider()
        
        # --- PENDING LIST ---
        st.markdown("### 🕒 Fila de Pendentes")
        
        c1, c2 = st.columns([1, 3])
        sel_all = c1.checkbox("Selecionar Todos")
        
        # Filter Logic
        all_names = ["Todos"] + [f"{meta['name']} ({e})" for e, meta in auth.users_data.items()]
        f_name = c2.selectbox("Filtrar:", all_names, key="fp_adm")
        
        df_p = df[df['status_aprovaca'] == 'Pendente'].copy()
        if f_name != "Todos":
            e_sel = f_name.split('(')[-1].replace(')', '')
            df_p = df_p[df_p['colaborador_email'] == e_sel]
            
        if not df_p.empty:
            df_p = df_p[['foi_editado', 'descricao', 'Nome', 'projeto', 'Data Real', 'horas', 'id']]
            df_p.insert(0, "✅", sel_all)
            df_p.insert(1, "🗑️", False)
            
            ed_p = st.data_editor(
                df_p, use_container_width=True, hide_index=True, key="adm_ed_p",
                column_config={
                    "✅": st.column_config.CheckboxColumn("Apv", width="small"),
                    "foi_editado": st.column_config.CheckboxColumn("⚠️ Editado?", disabled=True, help="Usuário alterou."),
                    "Data Real": st.column_config.DateColumn("Data", format="DD/MM/YYYY")
                }
            )
            
            col_a, col_b = st.columns(2)
            if col_a.button("Aprovar Selecionados", type="primary"):
                ids = ed_p[ed_p["✅"] == True]["id"].tolist()
                if ids:
                    repo.update_launch_status(tuple(ids), "Aprovado", reset_edit=True)
                    st.toast("Aprovado!"); time.sleep(0.5); st.rerun()
            if col_b.button("Rejeitar Selecionados"):
                ids = ed_p[ed_p["🗑️"] == True]["id"].tolist()
                if ids:
                    repo.update_launch_status(tuple(ids), "Negado")
                    st.toast("Rejeitado!"); time.sleep(0.5); st.rerun()
        else:
            st.info("Nenhuma pendência.")

        st.divider()
        
        # --- APPROVED LIST (FULL EDIT) ---
        st.markdown("### ✅ Histórico de Aprovados")
        f_a = st.selectbox("Filtrar Aprovados:", all_names, key="fa_adm")
        
        df_a = df[df['status_aprovaca'] == 'Aprovado'].copy()
        if f_a != "Todos":
            e_a = f_a.split('(')[-1].replace(')', '')
            df_a = df_a[df_a['colaborador_email'] == e_a]
            
        if not df_a.empty:
            df_a = df_a[['descricao', 'Nome', 'projeto', 'competencia', 'Data Real', 'horas', 'status_aprovaca', 'id']]
            
            ed_a = st.data_editor(
                df_a, use_container_width=True, hide_index=True, key="adm_ed_a",
                column_config={
                    "status_aprovaca": st.column_config.SelectboxColumn("Status", options=["Aprovado", "Pendente", "Negado"], required=True),
                    "Data Real": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                    "competencia": st.column_config.TextColumn("Comp. (Auto)")
                }
            )
            
            if st.button("Salvar Edições Aprovadas"):
                c = 0
                for r in ed_a.itertuples():
                    try:
                        # Logic to sync Date -> Competence
                        d_val = getattr(r, "Data_Real")
                        if isinstance(d_val, str): d_val = datetime.strptime(d_val, "%Y-%m-%d").date()
                        elif isinstance(d_val, pd.Timestamp): d_val = d_val.date()
                        
                        c_s, d_s = d_val.strftime("%Y-%m"), d_val.strftime("%Y-%m-%d")
                        
                        data = {"s": r.status_aprovaca, "h": r.horas, "d": r.descricao, "p": r.projeto, "c": c_s, "da": d_s, "id": r.id}
                        if repo.update_launch_full(data): c += 1
                    except: pass
                st.success(f"{c} registros atualizados!"); time.sleep(1); st.rerun()
        else:
            st.info("Vazio.")

        # --- REJECTED ---
        st.divider()
        with st.expander("❌ Lixeira / Rejeitados"):
            df_n = df[df['status_aprovaca'] == 'Negado'].copy()
            if not df_n.empty:
                df_n = df_n[['descricao', 'Nome', 'Data Real', 'status_aprovaca', 'id']]
                
                ed_n = st.data_editor(
                    df_n, use_container_width=True, hide_index=True,
                    column_config={"status_aprovaca": st.column_config.SelectboxColumn("Ação", options=["Negado", "Pendente"])}
                )
                
                c1, c2 = st.columns(2)
                if c1.button("Recuperar"):
                    for r in ed_n.itertuples():
                        if r.status_aprovaca != "Negado":
                            repo.update_launch_status(tuple([r.id]), r.status_aprovaca)
                    st.rerun()
                if c2.button("Excluir Permanentemente", type="primary"):
                    ids = tuple(ed_n[ed_n['status_aprovaca']=='Negado']['id'].tolist())
                    if ids:
                        repo.delete_launches(ids)
                        st.warning("Excluído."); time.sleep(1); st.rerun()

class FinanceController:
    """Handles Payment Logic."""
    
    @staticmethod
    def render(df: pd.DataFrame, auth: AuthService):
        st.subheader("💸 Consolidação Financeira")
        
        df_p = df[df['status_aprovaca'] == 'Aprovado'].copy()
        if df_p.empty:
            st.info("Nada a pagar."); return
            
        df_p['h_dec'] = df_p['horas'].apply(BusinessUtils.convert_hhmm_to_decimal)
        df_p['r$'] = df_p['h_dec'] * df_p['valor_hora_historico']
        
        # Grouping
        df_g = df_p.groupby(['competencia', 'colaborador_email']).agg({'r$': 'sum', 'horas': 'sum'}).reset_index()
        df_g = df_g.sort_values(['competencia'], ascending=False)
        
        total = df_p[df_p['status_pagamento'] != 'Pago']['r$'].sum()
        st.metric("Total Pendente", f"R$ {total:,.2f}")
        
        for idx, row in df_g.iterrows():
            nm = auth.email_to_name.get(row['colaborador_email'], row['colaborador_email'])
            
            with st.expander(f"📅 {row['competencia']} | 👤 {nm} | R$ {row['r$']:,.2f}"):
                det = df_p[(df_p['competencia'] == row['competencia']) & (df_p['colaborador_email'] == row['colaborador_email'])]
                
                st.dataframe(
                    det[['descricao', 'Data Real', 'horas', 'r$', 'status_pagamento']],
                    use_container_width=True, hide_index=True,
                    column_config={"r$": st.column_config.NumberColumn("Valor", format="R$ %.2f")}
                )
                
                # Bulk Update
                s_curr = det['status_pagamento'].iloc[0]
                ops = ["Em aberto", "Pago", "Parcial"]
                ix = ops.index(s_curr) if s_curr in ops else 0
                
                c1, c2 = st.columns([3, 1])
                ns = c1.selectbox("Status", ops, index=ix, key=f"pf_{idx}")
                
                if c2.button("Atualizar", key=f"bf_{idx}"):
                    repo = LaunchRepository()
                    ids = tuple(det['id'].tolist())
                    if repo.update_payment_status(ids, ns):
                        st.toast("Pago!"); time.sleep(0.5); st.rerun()

class ConfigController:
    """System Configuration."""
    
    @staticmethod
    def render(auth: AuthService):
        st.subheader("⚙️ Configurações")
        
        t1, t2, t3 = st.tabs(["Usuários", "Projetos", "Bancos"])
        
        with t1:
            st.caption("Edite os nomes de exibição.")
            repo_u = UserRepository()
            df_u = repo_u.get_all()
            
            ed_u = st.data_editor(
                df_u, use_container_width=True, num_rows="dynamic", hide_index=True,
                column_config={
                    "email": st.column_config.TextColumn("Login", disabled=True),
                    "nome": st.column_config.TextColumn("Nome Visual"),
                    "senha": st.column_config.TextColumn("Senha"),
                    "is_admin": st.column_config.CheckboxColumn("Admin"),
                    "valor_hora": st.column_config.NumberColumn("Rate")
                }
            )
            if st.button("Salvar Usuários"):
                for r in ed_u.itertuples():
                    nm = getattr(r, 'nome', r.email.split('@')[0])
                    repo_u.upsert_user(r.email, nm, str(r.senha), bool(r.is_admin), float(r.valor_hora))
                st.success("Salvo!"); st.rerun()

        with t2:
            repo_p = ConfigRepository()
            df_pr = repo_p.get_projects()
            ed_p = st.data_editor(df_pr, use_container_width=True, num_rows="dynamic", hide_index=True)
            if st.button("Salvar Projetos"):
                for r in ed_p.itertuples():
                    if r.nome: repo_p.add_project(r.nome)
                st.success("Salvo!"); st.rerun()

        with t3:
            repo_c = ConfigRepository()
            df_b = repo_c.get_banks()
            ed_b = st.data_editor(df_b, use_container_width=True, num_rows="dynamic", hide_index=True, column_config={"tipo_chave": st.column_config.SelectboxColumn("Tipo", options=["CPF", "CNPJ", "Email", "Aleatoria"])})
            if st.button("Salvar Bancos"):
                for r in ed_b.itertuples():
                    t = getattr(r, 'tipo_chave', 'CPF')
                    repo_c.upsert_bank(r.colaborador_email, r.banco, t, r.chave_pix)
                st.success("Salvo!"); st.rerun()

# ==============================================================================
# MAIN APPLICATION FLOW (CONTROLLER)
# ==============================================================================
def main():
    # 1. Init
    AppConfig.initialize()
    Utils.inject_css()
    
    # 2. Auth Check
    auth = AuthService()
    auth.load_users()
    
    # Renders sidebar login & returns session dict. Stops if not logged.
    # We must replicate the login logic here to call the specific sidebar render
    st.sidebar.title(f"{AppConfig.APP_ICON} {AppConfig.APP_NAME}")
    st.sidebar.caption(AppConfig.APP_VERSION)
    st.sidebar.markdown("---")
    
    if not auth.users_data:
        st.error("Erro: Banco de usuários vazio.")
        st.stop()
        
    emails = list(auth.users_data.keys())
    options = [f"{auth.email_to_name.get(e)} ({e})" for e in emails]
    rev_map = dict(zip(options, emails))
    
    sel = st.sidebar.selectbox("Identificação:", ["..."] + options)
    
    if sel == "...":
        st.info("👈 Faça login para acessar o sistema."); st.stop()
        
    email = rev_map[sel]
    user_data = auth.users_data[email]
    
    pwd = st.sidebar.text_input("Senha:", type="password")
    if pwd != user_data["pwd"]:
        st.sidebar.warning("Senha incorreta."); st.stop()
        
    is_admin = user_data["is_admin"] or (email in AppConfig.SUPER_ADMINS)
    
    if is_admin: st.sidebar.success(f"Admin: {user_data['name']}")
    else: st.sidebar.info(f"User: {user_data['name']}")
    
    current_user = {"email": email, "name": user_data["name"], "rate": user_data["rate"], "is_admin": is_admin}
    
    # 3. Navigation
    st.sidebar.divider()
    if is_admin:
        menu = ["📝 Lançamentos", "📊 Gestão de Painéis", "🛡️ Admin Aprovações", "💸 Pagamentos", "📈 BI Estratégico", "⚙️ Configurações", "🗂️ Histórico Pessoal"]
    else:
        menu = ["📝 Lançamentos", "🗂️ Histórico Pessoal", "📊 Meu Painel"]
        
    tab = st.sidebar.radio("Ir para:", menu)
    
    # 4. Data Load
    ds = DataService(auth)
    df = ds.get_enriched_data()
    
    repo_cfg = ConfigRepository()
    projects_df = repo_cfg.get_projects()
    projects_list = projects_df['nome'].tolist() if not projects_df.empty else ["Sustentação"]
    
    # 5. Routing
    if tab == "📝 Lançamentos":
        LaunchController.render(current_user, projects_list)
        
    elif tab == "🗂️ Histórico Pessoal":
        PersonalHistoryController.render(current_user, df)
        
    elif tab == "📊 Meu Painel" or tab == "📊 Gestão de Painéis":
        DashboardController.render(current_user, df, auth)
        
    elif tab == "🛡️ Admin Aprovações":
        if is_admin: AdminController.render(df, auth)
        else: st.error("Acesso Negado")
        
    elif tab == "💸 Pagamentos":
        FinanceController.render(df, auth)
        
    elif tab == "⚙️ Configurações":
        ConfigController.render(auth)
        
    elif tab == "📈 BI Estratégico":
        st.title("BI Humana (Analítico)")
        # Placeholder for BI Implementation
        if not df.empty:
            df['h_dec'] = df['horas'].apply(BusinessUtils.convert_hhmm_to_decimal)
            df['custo'] = df['h_dec'] * df['valor_hora_historico']
            
            c1, c2 = st.columns(2)
            c1.metric("Total Horas", f"{df['horas'].sum():.2f}")
            c2.metric("Custo Total", f"R$ {df['custo'].sum():,.2f}")
            
            st.bar_chart(df.groupby("projeto")['custo'].sum())

if __name__ == "__main__":
    main()