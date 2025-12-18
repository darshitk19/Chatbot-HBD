import streamlit as st
import re
import sqlite3

# ---------- Core search ----------
from core.bot_detector import is_bot
from core.sql_detector import needs_sql
from core.text_to_sql import generate_sql
from core.llm_router import route_user_input

from db.db import run_sql, rank_results
from db.config import DB_PATH
from ranking.explain import explain_business

# ---------- Owner features ----------
from business.business_by_phone import get_businesses_by_phone
from business.business_update import update_business
from business.business_health import get_update_suggestions
from business.business_add import add_business


def format_full_address(rec: dict) -> str:
    """Combine address, area, city, state into a single readable string."""
    parts = [
        rec.get("address"),
        rec.get("area"),
        rec.get("city"),
        rec.get("state"),
    ]
    parts = [str(p).strip() for p in parts if p and str(p).strip()]
    return ", ".join(parts) if parts else "N/A"


def get_recent_businesses(limit: int = 10):
    """
    Return most recently created businesses (latest first) for customers.
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, name, address, phone_number, website, category, city, state, area, created_at
        FROM google_maps_listings
        ORDER BY datetime(created_at) DESC
        LIMIT ?
        """,
        (limit,),
    )
    rows = cur.fetchall()
    conn.close()

    cols = [
        "id",
        "name",
        "address",
        "phone_number",
        "website",
        "category",
        "city",
        "state",
        "area",
        "created_at",
    ]
    return [dict(zip(cols, r)) for r in rows]


def get_owner_businesses(owner_email: str, limit: int = 10):
    """
    Businesses registered by a specific owner (latest first).
    Requires google_maps_listings to have an owner_email column;
    returns empty list if that column is not present.
    """
    if not owner_email:
        return []

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT id, name, address, phone_number, website, category, city, state, area, created_at
            FROM google_maps_listings
            WHERE owner_email = ?
            ORDER BY datetime(created_at) DESC
            LIMIT ?
            """,
            (owner_email, limit),
        )
    except sqlite3.OperationalError:
        # owner_email column missing – try to add it, then retry once
        try:
            cur.execute("ALTER TABLE google_maps_listings ADD COLUMN owner_email TEXT")
            conn.commit()
            cur.execute(
                """
                SELECT id, name, address, phone_number, website, category, city, state, area, created_at
                FROM google_maps_listings
                WHERE owner_email = ?
                ORDER BY datetime(created_at) DESC
                LIMIT ?
                """,
                (owner_email, limit),
            )
        except sqlite3.OperationalError:
            conn.close()
            return []

    rows = cur.fetchall()
    conn.close()

    cols = [
        "id",
        "name",
        "address",
        "phone_number",
        "website",
        "category",
        "city",
        "state",
        "area",
        "created_at",
    ]
    return [dict(zip(cols, r)) for r in rows]


def get_business_by_id(business_id: int):
    """Fetch full business record by its ID."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT * FROM google_maps_listings WHERE id = ?", (business_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return None
    cols = [d[0] for d in cur.description]
    conn.close()
    return dict(zip(cols, row))

# ---------- Online fallback ----------
from online.serpapi_search import search_online, rank_online_results
from online.missing_data_logger import log_missing_query


# ================= UI CONFIG =================
st.set_page_config(
    page_title="BusinessIQ Finder",
    page_icon="🔍",
    layout="wide"
)

st.title("🔍 BusinessIQ Finder")
st.caption("Find the best local businesses or manage your own listing in a few simple steps.")

# ================= SIMPLE AUTH & MODE SELECTION =================
if "user_phone" not in st.session_state:
    st.session_state.user_phone = None
if "user_role" not in st.session_state:
    st.session_state.user_role = None
if "nav" not in st.session_state:
    st.session_state.nav = "Home"
if "login_role_choice" not in st.session_state:
    st.session_state.login_role_choice = "Customer"

# ============ PAGE 1: LOGIN ONLY ============
if st.session_state.user_phone is None:
    with st.container(border=True):
        st.subheader("Login")
        st.caption("Use your mobile number or Owner ID and choose who you are to continue.")

        col1, col2 = st.columns([2, 2])

        with col1:
            phone_input = st.text_input(
                "Mobile number or Owner ID",
                placeholder="e.g. 9876543210 or OWN-123456",
            )

        with col2:
            st.markdown("**I am a...**")
            btn_col1, btn_col2 = st.columns(2)
            with btn_col1:
                if st.button(
                    "Customer",
                    type="primary" if st.session_state.login_role_choice == "Customer" else "secondary",
                ):
                    st.session_state.login_role_choice = "Customer"
            with btn_col2:
                if st.button(
                    "Business Owner",
                    type="primary" if st.session_state.login_role_choice == "Business Owner" else "secondary",
                ):
                    st.session_state.login_role_choice = "Business Owner"

        login_btn = st.button("Continue", type="primary")

        if login_btn:
            raw = (phone_input or "").strip()
            owner_key = ""

            if raw.upper().startswith("OWN-"):
                # login via Owner ID
                digits = re.sub(r"\D", "", raw[4:])
                owner_key = digits
            else:
                # login via mobile number
                owner_key = re.sub(r"\D", "", raw)

            if not owner_key:
                st.warning("Please enter your mobile number or Owner ID to continue.")
            elif len(owner_key) < 8:
                st.error("Please enter a valid mobile number or Owner ID.")
            else:
                st.session_state.user_phone = owner_key
                st.session_state.user_role = st.session_state.login_role_choice
                st.session_state.nav = "Home"
                st.success("Login successful. Loading your page...")
                st.rerun()

    st.stop()

# ============ PAGE 2: AFTER LOGIN ============
mode_label = (
    "🔍 Search Businesses" if st.session_state.user_role == "Customer"
    else "🏢 Business Owner"
)

# Sidebar navigation (Home / Profile) + simple help bot
st.sidebar.title("Menu")
st.session_state.nav = st.sidebar.radio(
    "Go to",
    ["Home", "Profile"],
    index=0 if st.session_state.nav == "Home" else 1,
)

st.sidebar.markdown("---")
st.sidebar.subheader("Help bot")
help_q = st.sidebar.text_input("Ask how to use BusinessIQ")
if help_q:
    q = help_q.lower().strip()
    # very simple normalization for typos / missing words
    q_tokens = re.findall(r"[a-z]+", q)

    def has_any(words):
        return any(w in q_tokens for w in words)

    role = st.session_state.user_role or "Customer"

    # CUSTOMER help
    if role == "Customer":
        if has_any({"search", "serch", "find", "look"}):
            st.sidebar.write(
                "To search for businesses: go to Home, type what you need in the "
                "search box (for example 'dentist in Mumbai'), and press Enter."
            )
        elif has_any({"profile", "profil", "account"}):
            st.sidebar.write(
                "To view your profile: use the sidebar 'Profile' page. "
                "It shows your email and role for this session."
            )
        elif has_any({"add", "ad"}) and has_any({"business", "bussiness", "biz"}):
            st.sidebar.write(
                "Adding or editing business listings is only for business owners. "
                "Log out and log in again as Business Owner to see those options."
            )
        else:
            st.sidebar.write(
                "I can help customers with:\n"
                "- how to search businesses\n"
                "- how to view profile\n"
                "Please ask a short question about these actions."
            )

    # BUSINESS OWNER help
    elif role == "Business Owner":
        if has_any({"add", "ad"}) and has_any({"business", "bussiness", "biz"}):
            st.sidebar.write(
                "To add your business: go to Home → '🏢 Business Owner' → 'Add your business' tab, "
                "fill in the business details form, and press 'Add Business'."
            )
        elif has_any({"change", "edit", "update"}) and has_any({"business", "bussiness", "listing"}):
            st.sidebar.write(
                "To edit your business details: go to Home → 'Find your business', "
                "enter your phone number, select your listing, and use "
                "'Update Business Profile' to save changes."
            )
        elif has_any({"profile", "profil", "account"}):
            st.sidebar.write(
                "To view your session profile: use the sidebar 'Profile' page "
                "to see your email and role."
            )
        else:
            st.sidebar.write(
                "I can help business owners with:\n"
                "- how to add your business\n"
                "- how to update business details\n"
                "- how to view your profile\n"
                "Please ask a short question about these actions."
            )

display_name = st.session_state.user_phone or "there"
display_name = display_name.strip()

top_col1, top_col2 = st.columns([3, 1])
with top_col1:
    if st.session_state.nav == "Home":
        if st.session_state.user_role == "Business Owner":
            st.subheader(f"Hi {display_name}, manage your business")
            st.caption("Find your business, update it, or add a new listing below.")
        else:
            st.subheader(f"Hi {display_name}, find local businesses")
            st.caption("Use the search box below to discover the best options for you.")
    else:
        st.subheader(f"Hi {display_name}")
with top_col2:
    if st.button("Logout"):
        st.session_state.user_phone = None
        st.session_state.user_role = None
        st.session_state.nav = "Home"
        st.rerun()

st.divider()

mode = mode_label

# =====================================================
# PROFILE PAGE (for both roles)
# =====================================================
if st.session_state.nav == "Profile":
    st.subheader("👤 Profile")
    st.write(f"**Mobile:** {st.session_state.user_phone}")
    st.write(f"**Role:** {st.session_state.user_role}")

    if st.session_state.user_role == "Business Owner":
        owner_id = (
            f"OWN-{(st.session_state.user_phone or '')[-6:]}"
            if st.session_state.user_phone
            else "N/A"
        )
        st.write(f"**Owner ID:** {owner_id}")

        st.markdown("### Your registered businesses")
        recent_profile = get_owner_businesses(st.session_state.user_phone, limit=10)
        if not recent_profile:
            st.caption("You have not registered any businesses yet using this login.")
        else:
            for b in recent_profile:
                with st.container(border=True):
                    st.markdown(f"**{b['name']}**")
                    st.caption(f"🆔 ID: {b.get('id') or 'N/A'}")
                    st.caption(f"📍 {format_full_address(b)}")
                    st.caption(f"📞 {b.get('phone_number') or 'N/A'}")
                    website = b.get("website") or "N/A"
                    if website != "N/A":
                        st.caption(f"🌐 {website}")
                    else:
                        st.caption("🌐 N/A")

# =====================================================
# 🔍 SEARCH MODE (CUSTOMERS)
# =====================================================
if st.session_state.nav == "Home" and mode == "🔍 Search Businesses":
    st.subheader("Search for Businesses")
    st.caption("Type what you are looking for (business name, service, area, category, etc.).")

    query = st.text_input("What are you looking for?", placeholder="e.g. dentist in Mumbai, cafes near Andheri, digital marketing agency")

    if query:
        if is_bot(query):
            st.error("🚫 Suspicious input detected")
            st.stop()

        # ---------- Decide SQL vs Chat ----------
        if needs_sql(query):
            sql = generate_sql(query)
            result = {
                "intent": "sql_search",
                "sql": sql,
                "response": "Here are the best matching businesses:"
            }
        else:
            result = route_user_input(query)

        st.markdown(f"💬 **Assistant:** {result['response']}")

        # ---------- SQL SEARCH ----------
        if result["intent"] == "sql_search" and result["sql"]:
            rows = run_sql(result["sql"])

            if rows:
                ranked = rank_results(rows, query)

                st.subheader("Top Matching Businesses (from our database)")

                for r in ranked:
                    with st.container(border=True):
                        st.markdown(f"### {r['name']}")

                        c1, c2, c3 = st.columns([3, 1.5, 1.5])

                        with c1:
                            st.write(f"📍 **Address:** {format_full_address(r)}")
                            st.write(f"🏷️ **Category:** {r.get('category','N/A')}")
                            st.write(f"🆔 **ID:** {r.get('id','N/A')}")

                        with c2:
                            st.write(f"⭐ **Rating:** {r.get('reviews_average','N/A')}")
                            st.write(f"🗣 **Reviews:** {r.get('reviews_count',0)}")

                        with c3:
                            st.write(f"📞 **Phone:** {r.get('phone_number') or 'N/A'}")
                            website = r.get('website') or 'N/A'
                            if website and website != 'N/A':
                                st.write(f"🌐 **Website:** [{website}]({website})")
                            else:
                                st.write("🌐 **Website:** N/A")

                        st.caption(f"👉 Why shown: {explain_business(r)}")
            else:
                st.info("No database results. Searching online...")
                online = rank_online_results(search_online(query))
                log_missing_query(query, online)

                st.subheader("Online Results")
                for r in online[:5]:
                    with st.container(border=True):
                        st.markdown(f"### {r.get('title','Unknown')}")
                        c1, c2, c3 = st.columns([3, 1.5, 1.5])

                        with c1:
                            st.write(f"📍 **Address:** {r.get('address','N/A')}")
                        with c2:
                            st.write(f"⭐ **Rating:** {r.get('rating','N/A')}")
                            st.write(f"🗣 **Reviews:** {r.get('reviews', 0)}")
                        with c3:
                            st.write(f"📞 **Phone:** {r.get('phone','N/A')}")
                            website = r.get('website') or 'N/A'
                            if website != 'N/A':
                                st.write(f"🌐 **Website:** [{website}]({website})")
                            else:
                                st.write("🌐 **Website:** N/A")

    # Always show a small recent section so customers see newest businesses
    with st.expander("Recently added businesses on BusinessIQ", expanded=False):
        recent = get_recent_businesses(limit=10)
        if not recent:
            st.caption("No businesses added yet.")
        else:
            for b in recent:
                with st.container(border=True):
                    st.markdown(f"**{b['name']}**")
                    st.caption(f"📍 {format_full_address(b)}")
                    st.caption(f"📞 {b.get('phone_number') or 'N/A'}")
                    website = b.get("website") or "N/A"
                    if website != "N/A":
                        st.caption(f"🌐 {website}")
                    else:
                        st.caption("🌐 N/A")
                    st.caption(f"🕒 Created at: {b.get('created_at','N/A')}")

# =====================================================
# 🏢 BUSINESS OWNER MODE (OWNERS)
# =====================================================
if st.session_state.nav == "Home" and mode == "🏢 Business Owner":
    st.markdown("### 🏢 Business owner tools")

    with st.expander("Your registered businesses (latest first)", expanded=False):
        recent = get_owner_businesses(st.session_state.user_phone, limit=10)
        if not recent:
            st.caption("You have not registered any businesses yet using this login.")
        else:
            for idx, b in enumerate(recent):
                with st.container(border=True):
                    st.markdown(f"**{b['name']}**")
                    st.caption(f"🆔 ID: {b.get('id') or 'N/A'}")
                    st.caption(f"📍 {format_full_address(b)}")
                    st.caption(f"📞 {b.get('phone_number') or 'N/A'}")
                    website = b.get("website") or "N/A"
                    if website != "N/A":
                        st.caption(f"🌐 {website}")
                    else:
                        st.caption("🌐 N/A")
                    st.caption(f"🕒 Created at: {b.get('created_at','N/A')}")

                    biz_id = b.get("id")
                    btn_key = f"owner_edit_{biz_id or 'row'+str(idx)}"
                    if biz_id is not None:
                        col_btn1, col_btn2 = st.columns([1, 4])
                        with col_btn1:
                            if st.button("✏️ Edit", key=btn_key):
                                st.session_state.owner_edit_id = biz_id
                                st.rerun()
                        with col_btn2:
                            if st.session_state.get("owner_edit_id") == biz_id:
                                st.success("👆 Edit form shown below")
    
    # Show edit form when owner_edit_id is set
    if st.session_state.get("owner_edit_id"):
        edit_biz_id = st.session_state.owner_edit_id
        edit_biz = get_business_by_id(edit_biz_id)
        
        if edit_biz:
            st.markdown("---")
            st.subheader(f"✏️ Edit Business: {edit_biz.get('name', 'Unknown')}")
            
            form_key_edit = f"edit_business_form_{edit_biz_id}"
            with st.form(form_key_edit):
                name_edit = st.text_input("Business Name", value=edit_biz.get("name", ""))
                address_edit = st.text_input("Address", value=edit_biz.get("address", ""))
                phone_edit = st.text_input("Phone Number", value=edit_biz.get("phone_number", ""))
                website_edit = st.text_input("Website", value=edit_biz.get("website", ""))
                category_edit = st.text_input("Category", value=edit_biz.get("category", ""))
                subcategory_edit = st.text_input("Subcategory", value=edit_biz.get("subcategory", ""))
                area_edit = st.text_input("Area / Locality", value=edit_biz.get("area", ""))
                city_edit = st.text_input("City", value=edit_biz.get("city", ""))
                state_edit = st.text_input("State", value=edit_biz.get("state", ""))
                
                col_save, col_cancel = st.columns([1, 1])
                with col_save:
                    save_edit = st.form_submit_button("💾 Save Changes", type="primary")
                with col_cancel:
                    cancel_edit = st.form_submit_button("❌ Cancel")
            
            # Handle form submission outside the form context
            if cancel_edit:
                st.session_state.owner_edit_id = None
                st.rerun()
            
            if save_edit:
                if not name_edit or not name_edit.strip():
                    st.error("Business Name is required.")
                else:
                    try:
                        # Use ID if available, otherwise use phone number
                        update_phone = phone_edit if phone_edit else edit_biz.get("phone_number", "")
                        result = update_business(
                            business_id=edit_biz_id,
                            phone_number=update_phone if edit_biz_id is None else None,
                            updates={
                                "name": name_edit,
                                "address": address_edit,
                                "phone_number": phone_edit,
                                "website": website_edit,
                                "category": category_edit,
                                "subcategory": subcategory_edit,
                                "area": area_edit,
                                "city": city_edit,
                                "state": state_edit,
                            },
                        )
                        if result:
                            st.success("✅ Business updated successfully!")
                            st.info("Changes have been saved to your business listing.")
                            st.session_state.owner_edit_id = None
                            st.rerun()
                        else:
                            st.warning("No changes were made. Please check your input.")
                    except Exception as e:
                        st.error(f"Error updating business: {str(e)}")
        else:
            st.warning(f"Business with ID {edit_biz_id} not found.")
            st.session_state.owner_edit_id = None

    tab_find, tab_add = st.tabs(["Find your business", "Add your business"])

    # ----- TAB 1: Find existing business -----
    with tab_find:
        st.subheader("📞 Verify Your Phone Number")

        phone = st.text_input(
            "Enter the phone number used in your business listing",
            placeholder="e.g. 9876543210"
        )

        if phone:
            businesses = get_businesses_by_phone(phone)

            if not businesses:
                st.warning("No businesses found for this phone number.")
            else:
                biz = businesses[0]  # assuming one business per phone

                st.success(f"Business found: **{biz['name']}**")

                biz_id = biz.get('id')
                if biz_id is not None:
                    st.markdown(f"**Business ID:** {biz_id}")
                st.markdown(f"**Address:** {format_full_address(biz)}")

                # ---------- HEALTH ----------
                st.subheader("📊 Business Health")

                suggestions = get_update_suggestions(biz)

                if suggestions:
                    for s in suggestions:
                        st.caption(f"⚠️ {s}")
                else:
                    st.caption("✅ Your business profile looks great!")

                # Show update form
                update_form_key = f"phone_update_form_{phone}"
                if update_form_key not in st.session_state:
                    st.session_state[update_form_key] = False
                
                if st.button("✏️ Update business details", key=f"phone_update_btn_{phone}"):
                    st.session_state[update_form_key] = True
                    st.rerun()
                
                if st.session_state.get(update_form_key, False):
                    # Refresh business data to get latest values
                    current_biz = biz
                    if biz.get("id") is not None:
                        refreshed_biz = get_business_by_id(biz["id"])
                        if refreshed_biz:
                            current_biz = refreshed_biz
                    
                    form_key = f"phone_update_business_form_{phone}"
                    with st.form(form_key):
                        st.markdown("**Edit your business details:**")
                        name_e = st.text_input("Business Name", value=current_biz.get("name", ""))
                        address_e = st.text_input("Address", value=current_biz.get("address", ""))
                        phone_e = st.text_input("Phone Number", value=current_biz.get("phone_number", ""))
                        website_e = st.text_input("Website", value=current_biz.get("website", ""))
                        category_e = st.text_input("Category", value=current_biz.get("category", ""))
                        subcategory_e = st.text_input("Subcategory", value=current_biz.get("subcategory", ""))
                        area_e = st.text_input("Area / Locality", value=current_biz.get("area", ""))
                        city_e = st.text_input("City", value=current_biz.get("city", ""))
                        state_e = st.text_input("State", value=current_biz.get("state", ""))

                        col_save, col_cancel = st.columns([1, 1])
                        with col_save:
                            save_e = st.form_submit_button("💾 Save Changes", type="primary")
                        with col_cancel:
                            cancel_e = st.form_submit_button("❌ Cancel")

                    # Handle form submission outside the form context
                    if cancel_e:
                        st.session_state[update_form_key] = False
                        st.rerun()

                    if save_e:
                        if not name_e or not name_e.strip():
                            st.error("Business Name is required.")
                        else:
                            try:
                                # Use ID if available, otherwise use phone number
                                update_phone = phone_e if phone_e else phone
                                result = update_business(
                                    business_id=biz.get("id"),
                                    phone_number=update_phone if biz.get("id") is None else None,
                                    updates={
                                        "name": name_e,
                                        "address": address_e,
                                        "phone_number": phone_e,
                                        "website": website_e,
                                        "category": category_e,
                                        "subcategory": subcategory_e,
                                        "area": area_e,
                                        "city": city_e,
                                        "state": state_e,
                                    },
                                )
                                if result:
                                    st.success("✅ Business updated successfully!")
                                    st.info("Updated details will help your business rank better. Refreshing...")
                                    st.session_state[update_form_key] = False
                                    st.rerun()
                                else:
                                    st.warning("No changes were made. Please check your input.")
                            except Exception as e:
                                st.error(f"Error updating business: {str(e)}")

    # ----- TAB 2: Add new business -----
    with tab_add:
        st.subheader("➕ Add Your Business")
        st.caption("If your business is not found, you can add it here so customers can discover you.")

        with st.form("add_business_form"):
            name_new = st.text_input("Business Name *")
            address_new = st.text_input("Address *")
            phone_new = st.text_input("Phone Number")
            website_new = st.text_input("Website")

            st.markdown("**Location details**")
            city_new = st.text_input("City")
            state_new = st.text_input("State")
            area_new = st.text_input("Area / Locality")

            st.markdown("**Category details**")
            category_new = st.text_input("Category (e.g. SEO Services)")
            subcategory_new = st.text_input("Subcategory (e.g. Marketing agency)")

            add_submit = st.form_submit_button("Add Business")

        if add_submit:
            if not name_new or not address_new:
                st.warning("Please fill in at least Business Name and Address.")
            else:
                new_id = add_business(
                    name=name_new,
                    address=address_new,
                    phone_number=phone_new,
                    website=website_new,
                    category=category_new,
                    subcategory=subcategory_new,
                    city=city_new,
                    state=state_new,
                    area=area_new,
                    owner_email=st.session_state.user_phone,
                )
                if new_id is not None:
                    st.success(f"✅ Business added or already registered. 🆔 ID: {new_id}")
                else:
                    st.success("✅ Business added or already registered.")
                st.info("You can now find it using the customer search just like any other business.")
