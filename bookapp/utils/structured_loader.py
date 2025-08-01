from bookapp.models import BookStructuredData

def store_structured_data_to_postgres(df, book_id, sheet_name="Sheet1"):
    df = df.fillna("")

    records = []
    for i, row in df.iterrows():
        for col in df.columns:
            records.append(BookStructuredData(
                book_id=book_id,
                sheet_name=sheet_name,
                row_index=i,
                column_name=str(col),
                value=str(row[col])
            ))
    BookStructuredData.objects.bulk_create(records)