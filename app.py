import streamlit as st
import tempfile
import pandas as pd
from main import PDFParser

st.set_page_config(page_title="PDF Table Extractor", page_icon="📄")

st.title("📄 PDF Table Extractor")

uploaded_file = st.file_uploader("Upload a PDF file", type=["pdf"])

if uploaded_file is not None:
    # save to a temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(uploaded_file.read())
        tmp_path = tmp.name

    st.info("Parsing PDF... this may take a while ⏳")

    try:
        parser = PDFParser(tmp_path)
        extracted_data = parser.parse_pdf()  # assume returns list of tables or dict

        # Convert to DataFrame for download (if not already)
        if isinstance(extracted_data, pd.DataFrame):
            df = extracted_data
        else:
            df = pd.DataFrame(extracted_data)

        st.success("✅ Parsing complete!")
        st.dataframe(df)

        # Download button
        csv_data = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Download CSV",
            data=csv_data,
            file_name="parsed_output.csv",
            mime="text/csv",
        )

    except Exception as e:
        st.error(f"❌ Error while parsing: {e}")
