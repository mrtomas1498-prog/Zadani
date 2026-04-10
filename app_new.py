import streamlit as st
import sqlalchemy
import pandas as pd
from datetime import date, datetime

# ============================================================
# 1. KONFIGURACE A PŘIPOJENÍ
# ============================================================
st.set_page_config(page_title="Zadávání a administrace zakázek", layout="wide")

DB_URL = "postgresql://postgres.oapirokgygazavkcajkp:tMdAUjH9yo66M5cE@aws-0-eu-west-1.pooler.supabase.com:6543/postgres"
engine = sqlalchemy.create_engine(DB_URL)

# ============================================================
# 2. DB FUNKCE
# ============================================================

def insert_order(cis, naz, obj, tel, te, jme, mes, typ='Standard'):
    try:
        with engine.begin() as conn:
            query = sqlalchemy.text("""
                INSERT INTO orders 
                (cislo_zakazky, nazev_zakazky, jmeno_zakazky, objem, telefon, termin_expedice, mesto, montaznik, typ_zakazky)
                VALUES (:cis, :naz, :jme, :obj, :tel, :te, :mes, 'Nezadáno', :typ)
            """)
            conn.execute(query, {
                "cis": cis, "naz": naz, "jme": jme, "obj": obj, 
                "tel": tel, "te": te, "mes": mes, "typ": typ
            })
        return True
    except Exception as e:
        st.error(f"Chyba při ukládání: {e}")
        return False

def load_orders():
    try:
        query = "SELECT cislo_zakazky, nazev_zakazky, jmeno_zakazky, objem, mesto, termin_expedice, telefon FROM orders ORDER BY termin_expedice DESC LIMIT 20"
        return pd.read_sql(query, engine)
    except Exception as e:
        return pd.DataFrame()

def load_pending_reclamations():
    try:
        # Načte pouze nevyřízené reklamace z druhé tabulky
        return pd.read_sql("SELECT * FROM reclamations WHERE vyrizeno = False ORDER BY id DESC", engine)
    except Exception as e:
        return pd.DataFrame()

def finalize_reclamation(recl_id, new_code, row_data):
    try:
        with engine.begin() as conn:
            # 1. Vytvoříme novou zakázku v hlavní tabulce (aby byla v zásobníku)
            conn.execute(sqlalchemy.text("""
                INSERT INTO orders (cislo_zakazky, nazev_zakazky, mesto, objem, typ_zakazky, montaznik)
                VALUES (:nc, :naz, :mes, :obj, 'Reklamace', 'Nezadáno')
            """), {
                "nc": new_code, "naz": row_data['nazev_zakazky'], 
                "mes": row_data['mesto'], "obj": row_data['objem']
            })
            # 2. Označíme reklamaci v archivu za vyřízenou
            conn.execute(sqlalchemy.text("UPDATE reclamations SET vyrizeno = True, nove_cislo = :nc WHERE id = :id"), 
                         {"nc": new_code, "id": recl_id})
        return True
    except Exception as e:
        st.error(f"Chyba při vyřizování reklamace: {e}")
        return False

# ============================================================
# 3. UI APLIKACE
# ============================================================
st.title("📦 Centrální správa zakázek")

tab1, tab2 = st.tabs(["🆕 Nová zakázka", "🛠️ Administrace reklamací"])

# --- TAB 1: ZADÁVÁNÍ NOVÝCH ZAKÁZEK ---
with tab1:
    with st.form("new_order_form", clear_on_submit=True):
        st.subheader("Vložit novou běžnou zakázku")
        c1, c2 = st.columns(2)
        with c1:
            cis = st.text_input("Číslo zakázky")
            naz = st.text_input("Název zakázky")
            jme = st.text_input("Jméno zákazníka")
            obj = st.text_input("Objem")
        with c2:
            mes = st.text_input("Město")
            tel = st.text_input("Telefon")
            te_text = st.text_input("Předpokládaný termín (DD.MM.RRRR)", value=date.today().strftime("%d.%m.%Y"))

        submit = st.form_submit_button("Uložit do databáze", use_container_width=True)

        if submit:
            try:
                te_final = datetime.strptime(te_text, "%d.%m.%Y").date()
                if cis and naz:
                    if insert_order(cis, naz, obj, tel, te_final.isoformat(), jme, mes):
                        st.success(f"✅ Zakázka {cis} uložena.")
                        st.rerun()
                else:
                    st.warning("⚠️ Číslo a název jsou povinné.")
            except:
                st.error("❌ Špatný formát data.")

    st.divider()
    st.subheader("📋 Poslední záznamy")
    st.dataframe(load_orders(), use_container_width=True, hide_index=True)

# --- TAB 2: ZPRACOVÁNÍ REKLAMACÍ ---
with tab2:
    st.subheader("🚨 Nahlášené reklamace. ")
    st.info("Zde vidíte seznam reklamací, které montážníci nahlásili. Přiřaďte jim nové číslo, aby se vrátily do plánu.")
    
    pending_recls = load_pending_reclamations()
    
    if pending_recls.empty:
        st.success("Aktuálně nejsou žádné nové reklamace k vyřízení.")
    else:
        for index, row in pending_recls.iterrows():
            with st.expander(f"REKLAMACE: Původní č. {row['puvodni_cislo']} - {row['mesto']}"):
                col_a, col_b = st.columns([2, 1])
                
                with col_a:
                    st.write(f"**Zákazník/Název:** {row['nazev_zakazky']}")
                    st.write(f"**Objem:** {row['objem']}")
                    st.write(f"**Nahlášeno:** {row['datum_vytvoreni'].strftime('%d.%m.%Y %H:%M')}")
                
                with col_b:
                    new_code = st.text_input("Přiřadit nové číslo zakázky:", key=f"re_code_{row['id']}", placeholder="např. {}-R".format(row['puvodni_cislo']))
                    if st.button("Vytvořit a poslat do plánu", key=f"re_btn_{row['id']}", type="primary", use_container_width=True):
                        if new_code:
                            if finalize_reclamation(row['id'], new_code, row):
                                st.success(f"Reklamace {new_code} byla odeslána k naplánování.")
                                st.rerun()
                        else:
                            st.error("Zadejte nové číslo!")