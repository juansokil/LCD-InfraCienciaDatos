import streamlit as st


st.set_page_config(
    page_title="ARS Exchange Monitor",
    page_icon="AR",
    layout="wide",
)

navigation = st.navigation(
    [
        st.Page("home_page.py", title="Inicio", icon=":material/home:"),
        st.Page("dashboard_page.py", title="Dashboard", icon=":material/bar_chart:"),
    ]
)

navigation.run()
