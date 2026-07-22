#This script uploads the latest version of the prb_bins to the database.
#  It should be run after the prb_bins scripts have been exectured 

import logging
import pandas as pd
from connectors import devo

from settings import PROB_BINS_INPUT_DIR, table_storage_path

logging.basicConfig(level=logging.INFO)


def append_latest_pq_to_table(datalab, table_name, pq_name, local_pq_path):
    """ Uploads the latest parquet file to the S3 folder of the table and then recreates the table from the underlying parquet files to update the schema in case there are new variables in the latest pq.

    Args:
        datalab (str): Name of the datalab where the table is located
        table_name (str): Name of the table to which the new parquet file will be appended
        pq_name (str): Name of the parquet file to be uploaded (without path)
        local_pq_path (str): Local path to the parquet file to be uploaded. Can be a .parquet, .csv or .xlsx file. If the file is not a .parquet, it will be converted to .parquet before uploading.
    """
    #if the local_pq_path is not a parquet but csv rather than parquet, read the csv and convert it to parquet before uploading
    if local_pq_path.endswith('.csv'):
        df_csv = pd.read_csv(local_pq_path)
        local_pq_path = local_pq_path.replace('.csv', '.parquet')
        df_csv.to_parquet(local_pq_path, index=False)
    if local_pq_path.endswith('.xlsx'):
        df_xlsx = pd.read_excel(local_pq_path, engine='openpyxl')
        local_pq_path = local_pq_path.replace('.xlsx', '.parquet')
        df_xlsx.to_parquet(local_pq_path, index=False)
    
    df_pq = pd.read_parquet(local_pq_path)

    destination_pq_path = table_storage_path(datalab, table_name, pq_name)

    #check that the nwe parquet has the same columns as the existing table, if not log a warning message
    try:
        existing_columns = devo.read_sql(f"SELECT * FROM lab_{datalab}.{table_name} LIMIT 1").columns
        new_columns = df_pq.columns
        if set(existing_columns) != set(new_columns):
            logging.warning(f"Column mismatch: existing table has columns {existing_columns}, while the new parquet file has columns {new_columns}. Please check if this is expected.")

    except: 
        logging.warning(f"Could not read existing table lab_{datalab}.{table_name} to compare columns. Please check if the table exists and if the connection to DEVO is working properly.")
        
    
    #check that the two parquets have the same schema, if not log a warning message
    try:
        existing_schema = devo.read_sql(f"DESCRIBE lab_{datalab}.{table_name}").set_index('name')['type']
        new_schema = df_pq.dtypes
        if not existing_schema.equals(new_schema):
            logging.warning(f"Schema mismatch: existing table has schema {existing_schema}, while the new parquet file has schema {new_schema}. Please check if this is expected.")
    except:
        logging.warning(f"Could not read existing table lab_{datalab}.{table_name} to compare schema. Please check if the table exists and if the connection to DEVO is working properly.")
    #upload the new parquet file to the S3 folder of the table
    logging.info(f"Uploading {pq_name} to {destination_pq_path}")
    devo.to_parquet(
        df=df_pq,
        path = destination_pq_path,
    )

    #after uploading the new pq, the table has to be recreated from the underlying parquet files to update the schema in case there are new variables in the latest pq.
    logging.info(f'Dropping table lab_{datalab}.{table_name} and recreating it from the underlying parquet files to update the schema if needed.')
    devo.drop_table(f"lab_{datalab}.{table_name}", if_exists=True)
    devo.read_sql(f"CREATE EXTERNAL TABLE lab_{datalab}.{table_name} LIKE PARQUET '{destination_pq_path}' STORED AS PARQUET LOCATION '{destination_pq_path.rsplit('/', 1)[0]}/';")

#UPDATE pq_name & local_pq_path
if __name__ == "__main__":
    datalab = "prj_ces"
    #table_name = "core_uncertainty_prb_bins"
    table_name = "core_uncertainty_probbins"
    pq_name = "ces_uncertainty_10_wave_77.parquet"
    # Produced by the upstream MATLAB step; see CES_PROB_BINS_INPUT_DIR.
    local_pq_path = str(PROB_BINS_INPUT_DIR / "CES_uncertainty_10_NEW_w77.csv")

    append_latest_pq_to_table(datalab, table_name, pq_name, local_pq_path)