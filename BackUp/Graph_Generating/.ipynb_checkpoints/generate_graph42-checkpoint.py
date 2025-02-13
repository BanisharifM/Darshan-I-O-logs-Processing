import pandas as pd
import yaml
import os
import logging
from sklearn.model_selection import train_test_split

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def load_graph_structure(yaml_file_path):
    logging.info(f"Loading graph structure from {yaml_file_path}")
    with open(yaml_file_path, 'r') as file:
        return yaml.safe_load(file)

def save_graph_data(output_dir, output_file, data, total_rows, attributes):
    os.makedirs(output_dir, exist_ok=True)
    if os.path.exists(output_file):
        os.remove(output_file)

    graph_data = []
    total_processed_rows = 0

    for idx, row in data.iterrows():
        # For each attribute, create a link to the tag
        for attr in attributes:
            graph_row = {
                'graph_index': total_processed_rows,
                'tag_value': row['tag'],
                'node_id': attr,
                'node_value': row[attr]
            }
            graph_data.append(graph_row)
        total_processed_rows += 1

        if total_processed_rows >= total_rows:
            break

    # Convert list of dictionaries to DataFrame and save to CSV file
    graph_df = pd.DataFrame(graph_data)
    graph_df.to_csv(output_file, mode='a', header=not os.path.exists(output_file), index=False)
    logging.info(f"All graphs saved to {output_file}.")

def load_and_process_data(train_file_path, total_rows, yaml_file_path, test_size=0.5, log_interval=1000):
    # Load graph structure from YAML file
    graph_structure = load_graph_structure(yaml_file_path)
    attributes = list(graph_structure['tag'].keys())
    logging.info("Graph structure loaded successfully.")

    # Load dataset
    logging.info(f"Loading dataset from {train_file_path}")
    data = pd.read_csv(train_file_path)

    # Split dataset into training and testing sets
    logging.info(f"Splitting dataset into training and testing sets with test size = {test_size}")
    train_data, test_data = train_test_split(data, test_size=test_size, random_state=1)

    # Save training graph data
    logging.info(f"Processing training data with {len(train_data)} rows.")
    output_dir = 'Graphs/Graph42'
    output_file = os.path.join(output_dir, 'train_graphs.csv')
    save_graph_data(output_dir, output_file, train_data, total_rows, attributes)

    # Save testing graph data
    logging.info(f"Processing testing data with {len(test_data)} rows.")
    output_dir = 'Graphs/Graph42'
    output_file = os.path.join(output_dir, 'test_graphs.csv')
    save_graph_data(output_dir, output_file, test_data, total_rows, attributes)

# Define path to your training data CSV file
train_file_path = 'CSVs/sample_train.csv'
yaml_file_path = "Graphs/Graph42/graph_structure.yaml"
total_rows = 10000  # You can adjust this value as needed

logging.info("Starting data processing.")
load_and_process_data(train_file_path, total_rows, yaml_file_path, log_interval=1000)
logging.info("Data processing completed.")
