import streamlit as st
import pandas as pd
import pdfplumber
import plotly.express as px

# ---------------------------------------------------------
# Numeric coercion settings (tweakable)
# ---------------------------------------------------------
# Characters stripped from text before trying to read it as a number,
# e.g. "$1,234.56" -> 1234.56 and "45%" -> 45
NUMERIC_STRIP_PATTERN = r"[$,%\s]"
# A text column is converted to numeric only if at least this share
# (0.0 - 1.0) of its non-blank values parse as numbers, so genuinely
# categorical columns are left alone.
MIN_NUMERIC_RATIO = 0.8


def coerce_numeric_columns(df):
    """Convert text columns that are really numbers.

    pdfplumber returns every PDF cell as text, so numeric columns arrive
    as strings and the charts section would skip them. This tries to read
    each text column as numbers after stripping common formatting. A column
    is converted only if at least MIN_NUMERIC_RATIO of its non-blank
    values parse as numbers.
    """
    df = df.copy()
    text_cols = [
        c for c in df.columns
        if pd.api.types.is_string_dtype(df[c].dtype)
    ]
    for col in text_cols:
        series = df[col].astype("string")
        non_blank = series.str.strip()
        non_blank = non_blank[non_blank.notna() & (non_blank != "")]
        if non_blank.empty:
            continue
        cleaned = non_blank.str.replace(NUMERIC_STRIP_PATTERN, "", regex=True)
        parsed = pd.to_numeric(cleaned, errors="coerce")
        if parsed.notna().mean() >= MIN_NUMERIC_RATIO:
            df[col] = pd.to_numeric(
                series.str.strip().str.replace(
                    NUMERIC_STRIP_PATTERN, "", regex=True
                ),
                errors="coerce",
            )
    return df


st.title("File to Table")

uploaded = st.file_uploader(
    "Upload CSV, XLSX, or PDF",
    type=["csv", "xlsx", "pdf"]
)

if uploaded:
    name = uploaded.name.lower()

    # ---------------------------------------------------------
    # CSV
    # ---------------------------------------------------------
    if name.endswith(".csv"):
        try:
            df = pd.read_csv(uploaded)
        except Exception as e:
            st.error(f"Error reading CSV: {e}")
            st.stop()

    # ---------------------------------------------------------
    # Excel
    # ---------------------------------------------------------
    elif name.endswith(".xlsx"):
        try:
            df = pd.read_excel(uploaded)
        except Exception as e:
            st.error(f"Error reading Excel file: {e}")
            st.stop()

    # ---------------------------------------------------------
    # PDF
    # ---------------------------------------------------------
    else:
        try:
            tables = []

            with pdfplumber.open(uploaded) as pdf:
                for page in pdf.pages:
                    extracted_tables = page.extract_tables() or []
                    tables.extend(extracted_tables)

            # No tables found
            if not tables:
                st.warning("No tables found in this PDF.")
                st.stop()

            # More than one table found
            if len(tables) > 1:
                choice = st.selectbox(
                    f"Found {len(tables)} tables - pick one to view:",
                    range(len(tables)),
                    format_func=lambda i: (
                        f"Table {i + 1} "
                        f"({max(len(tables[i]) - 1, 0)} rows x "
                        f"{len(tables[i][0]) if tables[i] else 0} columns)"
                    )
                )

                merge = st.checkbox("Merge all tables into one")

                if merge:
                    frames = []

                    for table in tables:
                        if table and len(table) > 1:
                            frame = pd.DataFrame(
                                table[1:],
                                columns=table[0]
                            )
                            frames.append(frame)

                    if not frames:
                        st.warning("No usable table data was found.")
                        st.stop()

                    try:
                        df = pd.concat(
                            frames,
                            ignore_index=True
                        )

                        st.success(
                            f"Merged {len(frames)} tables "
                            f"into {len(df)} rows."
                        )

                    except ValueError:
                        st.error(
                            "The tables could not be merged automatically."
                        )
                        st.stop()

                else:
                    selected_table = tables[choice]

                    if not selected_table or len(selected_table) < 2:
                        st.warning(
                            "The selected table does not contain usable data."
                        )
                        st.stop()

                    df = pd.DataFrame(
                        selected_table[1:],
                        columns=selected_table[0]
                    )

            # Exactly one table found
            else:
                table = tables[0]

                if not table or len(table) < 2:
                    st.warning(
                        "The table does not contain usable data."
                    )
                    st.stop()

                df = pd.DataFrame(
                    table[1:],
                    columns=table[0]
                )

        except Exception as e:
            st.error(f"Unexpected error reading the PDF: {e}")
            st.stop()

    # ---------------------------------------------------------
    # Coerce text-that-is-really-numbers (mainly from PDFs)
    # ---------------------------------------------------------
    df = coerce_numeric_columns(df)

    # ---------------------------------------------------------
    # Display loaded data
    # ---------------------------------------------------------
    st.success(
        f"Loaded {len(df)} rows x {len(df.columns)} columns"
    )

    st.dataframe(
        df,
        use_container_width=True
    )

    # ---------------------------------------------------------
    # Download as CSV
    # ---------------------------------------------------------
    csv_data = df.to_csv(index=False)

    st.download_button(
        label="Download as CSV",
        data=csv_data,
        file_name="table.csv",
        mime="text/csv"
    )

    # ---------------------------------------------------------
    # Column type detection
    # ---------------------------------------------------------
    numeric_cols = (
        df.select_dtypes(include="number")
        .columns
        .tolist()
    )

    categorical_cols = (
        df.select_dtypes(
            include=["object", "category"]
        )
        .columns
        .tolist()
    )

    # ---------------------------------------------------------
    # Quick charts
    # ---------------------------------------------------------
    if numeric_cols:
        st.subheader("Quick Charts")

        chart_type = st.radio(
            "Chart type",
            ["Histogram", "Box Plot"],
            horizontal=True
        )

        col = st.selectbox(
            "Numeric column",
            numeric_cols
        )

        # Initial chart
        if chart_type == "Histogram":
            fig = px.histogram(
                df,
                x=col,
                nbins=30
            )
        else:
            fig = px.box(
                df,
                y=col
            )

        st.plotly_chart(
            fig,
            use_container_width=True
        )

        # -----------------------------------------------------
        # Optional grouping
        # -----------------------------------------------------
        if categorical_cols:
            group_col = st.selectbox(
                "Group by (optional)",
                ["(none)"] + categorical_cols
            )

            if group_col != "(none)":

                if chart_type == "Histogram":
                    grouped_fig = px.histogram(
                        df,
                        x=col,
                        color=group_col,
                        barmode="overlay",
                        opacity=0.6
                    )

                else:
                    grouped_fig = px.box(
                        df,
                        y=col,
                        color=group_col
                    )

                st.plotly_chart(
                    grouped_fig,
                    use_container_width=True
                )

    else:
        st.info(
            "No numeric columns detected - "
            "charts need at least one number column."
        )
