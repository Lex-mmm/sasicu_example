import streamlit as st
from pathlib import Path

st.set_page_config(page_title="SDC Digital Twin Monitor", layout="wide")

st.title("SDC Digital Twin Medical Monitoring System")

st.info(
    "This Streamlit app shows project information and release notes.\n\n"
    "The full Tkinter-based GUI (sdc_monitor_control.py) cannot run on Streamlit Cloud "
    "because Tkinter requires a desktop display, which isn't available in the headless server."
)

# Read release notes if available
notes_path = Path("RELEASE_NOTES.md")
if notes_path.exists():
    st.subheader("Release Notes")
    st.markdown(notes_path.read_text())
else:
    st.subheader("Release Notes")
    st.write("No release notes found.")

st.subheader("How to run the full GUI locally")
st.code("""
# In a local terminal
pip install -r requirements.txt
python3 sdc_monitor_control.py
""", language="bash")

st.subheader("Project Files")
for p in sorted(Path(".").glob("*.py")):
    st.write("-", p.name)

st.caption("© 2025 Dr. L.M. van Loon. Academic and educational use permitted.")
