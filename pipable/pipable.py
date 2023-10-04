# pipable/pipable.py
"""Pipable: A Python package for connecting to a remote PostgreSQL server, generating and executing the natural langauge based data 
search queries which are mapped to SQL queries using a using the pipLLM.

This module provides classes and functions for connecting to a PostgreSQL database and using a language model to generate SQL queries.

"""

from pandas import DataFrame

from .core.dev_logger import dev_logger
from .core.postgresql_connector import PostgresConfig, PostgresConnector
from .interfaces.database_connector_interface import DatabaseConnectorInterface
from .interfaces.llm_api_client_interface import LlmApiClientInterface
from .llm_client.pipllm import PipLlmApiClient


class Pipable:
    """A class for connecting to a remote PostgreSQL server and executing SQL queries using llm.

    This class provides methods for establishing a connection to a remote PostgreSQL server
    and using a language model to generate SQL queries.
    """

    def __init__(
        self,
        database_connector: DatabaseConnectorInterface,
        llm_api_client: LlmApiClientInterface,
    ):
        """Initialize a Pipable instance.

        Args:
            postgres_config (PostgresConfig): The configuration for connecting to the PostgreSQL server.
            llm_api_base_url (str): The base URL of the language model API.
        """
        self.database_connector = database_connector
        self.llm_api_client = llm_api_client
        self.connected = False
        self.connection = None
        self.logger = dev_logger()
        self.logger.info("logger initialized in Pipable")
        self.all_table_queries = None  # Store create table queries for all tables

    def _generate_sql_query(self, context, question):
        self.logger.info("generating query using llm")
        generated_text = self.llm_api_client.generate_text(context, question)
        if not generated_text:
            self.logger.error(f"LLM failed to generate a SQL query: {e}")
            raise ValueError("LLM failed to generate a SQL query.")
        return generated_text.strip()

    def connect(self):
        """Establish a connection to the Database server.

        This method establishes a connection to the remote PostgreSQL server using the provided database connector.

        Raises:
            ConnectionError: If the connection to the server cannot be established.
        """
        if not self.connected:
            try:
                self.database_connector.connect()
                self.connected = True
            except Exception as e:
                self.logger.error(f"Failed to connect to the database: {str(e)}")
                raise ConnectionError("Failed to connect to the database.")

    def disconnect(self):
        """Close the connection to the Database server.

        This method closes the connection to the remote PostgreSQL server.
        """
        if self.connected:
            try:
                self.database_connector.disconnect()
                self.connected = False
            except Exception as e:
                self.logger.error(f"Failed to disconnect from the database: {str(e)}")
                raise ConnectionError("Failed to disconnect from the database.")

    def _generate_create_table_statements(self, table_names=None):
        """Generate CREATE TABLE statements for the specified tables or all tables in the database."""
        if self.all_table_queries is not None:
            return self.all_table_queries
        # Check if specific table names are provided, else get all tables
        if table_names is not None and len(table_names) > 0:
            tables_to_fetch = ",".join([f"'{table}'" for table in table_names])
            where_clause = f"WHERE table_name IN ({tables_to_fetch})"
        else:
            where_clause = "WHERE table_schema = 'public'"

        # SQL query to extract column names and data types
        column_info_query = f"""
        SELECT table_name, column_name, data_type
        FROM information_schema.columns
        {where_clause};
        """

        try:
            # Execute the SQL query using the database connector and get the result as DataFrame
            column_info_df = self.database_connector.execute_query(column_info_query)

            # Group column info by table name using Pandas groupby
            grouped_columns = column_info_df.groupby("table_name").apply(
                lambda x: ", ".join(
                    [
                        f"{row['column_name']} {row['data_type']}"
                        for _, row in x.iterrows()
                    ]
                )
            )

            # Generate CREATE TABLE statements in Python
            self.all_table_queries = [
                f"CREATE TABLE {table_name} ({columns});"
                for table_name, columns in grouped_columns.items()
            ]

            return self.all_table_queries
        except Exception as e:
            self.logger.error(f"Error generating CREATE TABLE statements: {str(e)}")
            raise ValueError("Error generating CREATE TABLE statements.")

    def ask(self, question=None, table_names=None) -> DataFrame:
        """Generate an SQL query and execute it on the PostgreSQL server.

        Args:
            table_names (list, optional): The list of table names for the query context.
            If not provided, it will be auto-generated.
            question (str, optional): The query to perform in simple English.

        Returns:
            pandas.DataFrame: A DataFrame containing the query result.

        Raises:
            ValueError: If the language model does not generate a valid SQL query.
        """
        try:
            # Connect to PostgreSQL if not already connected
            self.connect()

            # Generate CREATE TABLE statements for the specified tables or all tables
            create_table_statements = self._generate_create_table_statements(
                table_names
            )
            # Concatenate create table statements into a single line for context
            context = " ".join(create_table_statements)

            # Generate SQL query from LLM
            sql_query = self._generate_sql_query(context, question)

            # Execute SQL query
            result_df = self.database_connector.execute_query(sql_query)

            return result_df
        except Exception as e:
            raise Exception(f"Error in 'ask' method: {str(e)}")