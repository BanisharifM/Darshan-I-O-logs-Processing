import os
import pandas as pd
import torch
import torch.nn.functional as F
from torch_geometric.data import Data
from torch_geometric.loader import DataLoader
from torch_geometric.nn import GCNConv, global_mean_pool
from torch.optim.lr_scheduler import ReduceLROnPlateau
import matplotlib.pyplot as plt
import logging
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from sklearn.preprocessing import StandardScaler
import numpy as np
import signal
import sys

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Define the updated GNN model with pooling and a fully connected layer for tag prediction
class EnhancedGNN(torch.nn.Module):
    def __init__(self, num_node_features):
        super(EnhancedGNN, self).__init__()
        self.conv1 = GCNConv(num_node_features, 64)
        self.conv2 = GCNConv(64, 128)
        self.conv3 = GCNConv(128, 64)
        self.dropout = torch.nn.Dropout(p=0.5)
        self.fc = torch.nn.Linear(64, 1)  # Fully connected layer to predict the 'tag'

    def forward(self, data):
        x, edge_index, edge_weight, batch = data.x, data.edge_index, data.edge_weight, data.batch
        x = self.conv1(x, edge_index, edge_weight=edge_weight)
        x = F.relu(x)
        x = self.dropout(x)
        x = self.conv2(x, edge_index, edge_weight=edge_weight)
        x = F.relu(x)
        x = self.dropout(x)
        x = self.conv3(x, edge_index, edge_weight=edge_weight)
        x = F.relu(x)
        x = self.dropout(x)
        # Pooling layer to aggregate node features across the graph
        x = global_mean_pool(x, batch)
        # Fully connected layer to predict the tag
        x = self.fc(x)
        return x  # Output a single prediction for the tag

# Load data from CSV files and create PyTorch Geometric Data objects
def load_data(file_path):
    df = pd.read_csv(file_path)

    # Remove non-numerical columns like column headers from the dataset
    graphs = []
    scaler = StandardScaler()

    # Exclude the 'tag' column (which is the target) and any non-numerical columns (e.g., 'graph_index')
    feature_columns = df.columns.drop(['graph_index', 'tag'])  # Adjust 'graph_index' to your actual index column if needed

    for graph_index in df['graph_index'].unique():
        graph_df = df[df['graph_index'] == graph_index]
        
        # Extract node features and standardize them
        node_features = graph_df[feature_columns].values.astype(np.float64)  # Ensure float64 precision
        node_features = scaler.fit_transform(node_features)
        # x = torch.tensor(node_features, dtype=torch.float)  # Convert to tensor with float precision
        x = torch.tensor(node_features, dtype=torch.double)  # Use double precision (float64) in PyTorch


        # Extract edges and remove duplicates (considering undirected graph)
        edges = graph_df[['node_id_1', 'node_id_2']].values
        edge_weight = graph_df['edge_weight'].values
        edge_index = []
        edge_weight_final = []
        
        # Use a dictionary to map string-based node IDs to unique indices
        node_mapping = {}
        current_index = 0
        
        seen_edges = set()
        for i, (n1, n2) in enumerate(edges):
            if n1 not in node_mapping:
                node_mapping[n1] = current_index
                current_index += 1
            if n2 not in node_mapping:
                node_mapping[n2] = current_index
                current_index += 1
            
            idx1 = node_mapping[n1]
            idx2 = node_mapping[n2]
            edge = tuple(sorted((idx1, idx2)))
            
            if edge not in seen_edges:
                seen_edges.add(edge)
                edge_index.append([idx1, idx2])
                edge_index.append([idx2, idx1])  # Add the reverse edge for undirected graph
                edge_weight_final.append(edge_weight[i])
                edge_weight_final.append(edge_weight[i])

        edge_index = torch.tensor(edge_index, dtype=torch.long).t().contiguous()
        # edge_weight = torch.tensor(edge_weight_final, dtype=torch.float)
        edge_weight = torch.tensor(edge_weight_final, dtype=torch.double)

        # Target value (the tag column)
        y_value = float(graph_df['tag'].iloc[0])  # 'tag' is the column name for the target
        # y = torch.tensor([y_value], dtype=torch.float).view(1, -1)  # Ensure target is of shape [1, 1]
        y = torch.tensor([y_value], dtype=torch.double).view(1, -1)  # Use double precision for target value

        data = Data(x=x, edge_index=edge_index, edge_weight=edge_weight, y=y)
        graphs.append(data)

    return graphs

# Define paths to the data files
train_file_path = "Graphs/Graph110/train_graphs.csv"
test_file_path = "Graphs/Graph110/test_graphs.csv"

# Load the data
train_data = load_data(train_file_path)
test_data = load_data(test_file_path)

# Hyperparameters
num_epochs = 100
batch_size = 64
learning_rate = 0.001
weight_decay = 1e-4

# Create data loader
train_loader = DataLoader(train_data, batch_size=batch_size, shuffle=True)
test_loader = DataLoader(test_data, batch_size=batch_size, shuffle=False)

# Initialize the model, optimizer, and loss function
num_node_features = len(train_data[0].x[0])  # Number of node features based on dataset
model = EnhancedGNN(num_node_features)
optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate, weight_decay=weight_decay)
scheduler = ReduceLROnPlateau(optimizer, 'min', factor=0.5, patience=10, min_lr=1e-6)
criterion = torch.nn.L1Loss()

# Checkpointing function
def save_checkpoint(epoch, model, optimizer, scheduler, train_losses, train_rmse_scores, test_rmse_scores, train_mae_scores, test_mae_scores, train_r2_scores, test_r2_scores, checkpoint_path):
    torch.save({
        'epoch': epoch,
        'model_state_dict': model.state_dict(),
        'optimizer_state_dict': optimizer.state_dict(),
        'scheduler_state_dict': scheduler.state_dict(),
        'train_losses': train_losses,
        'train_rmse_scores': train_rmse_scores,
        'test_rmse_scores': test_rmse_scores,
        'train_mae_scores': train_mae_scores,
        'test_mae_scores': test_mae_scores,
        'train_r2_scores': train_r2_scores,
        'test_r2_scores': test_r2_scores,
    }, checkpoint_path)

def load_checkpoint(checkpoint_path, model, optimizer, scheduler):
    if os.path.exists(checkpoint_path):
        checkpoint = torch.load(checkpoint_path)  # Use the default (weights_only=False)
        model.load_state_dict(checkpoint['model_state_dict'])
        optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
        scheduler.load_state_dict(checkpoint['scheduler_state_dict'])
        epoch = checkpoint['epoch']
        train_losses = checkpoint['train_losses']
        train_rmse_scores = checkpoint['train_rmse_scores']
        test_rmse_scores = checkpoint['test_rmse_scores']
        train_mae_scores = checkpoint['train_mae_scores']
        test_mae_scores = checkpoint['test_mae_scores']
        train_r2_scores = checkpoint['train_r2_scores']
        test_r2_scores = checkpoint['test_r2_scores']
        logging.info(f'Loaded checkpoint from {checkpoint_path}, starting at epoch {epoch + 1}')
        return epoch, train_losses, train_rmse_scores, test_rmse_scores, train_mae_scores, test_mae_scores, train_r2_scores, test_r2_scores
    else:
        return 0, [], [], [], [], [], [], []

def log_predictions(predictions, targets, epoch, phase):
    log_dir = 'Graphs/Graph110/logs'
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    log_file = os.path.join(log_dir, f'{phase}_predictions.csv')

    if os.path.exists(log_file):
        df = pd.read_csv(log_file)
        new_df = pd.DataFrame({
            'Epoch': [epoch] * len(predictions),
            'Target': targets,
            'Prediction': predictions
        })
        df = pd.concat([df, new_df], ignore_index=True)
    else:
        df = pd.DataFrame({
            'Epoch': [epoch] * len(predictions),
            'Target': targets,
            'Prediction': predictions
        })
    
    df.to_csv(log_file, index=False)

# def load_tags(tags_file):
#     return pd.read_csv(tags_file, index_col='graph_index')

# # Training function
# def train(model, train_loader, test_loader, criterion, optimizer, scheduler, num_epochs, checkpoint_path, update_logs_and_charts):
#     start_epoch, train_losses, train_rmse_scores, test_rmse_scores, train_mae_scores, test_mae_scores, train_r2_scores, test_r2_scores = load_checkpoint(checkpoint_path, model, optimizer, scheduler)

#     for epoch in range(start_epoch, num_epochs):
#         model.train()
#         total_loss = 0
#         for data in train_loader:
#             optimizer.zero_grad()
#             output = model(data).view(-1)  # Flatten the output
#             loss = criterion(output, data.y.view(-1))  # Flatten the target
#             loss.backward()
#             optimizer.step()
#             total_loss += loss.item() * data.num_graphs

#         train_loss = total_loss / len(train_loader.dataset)
#         train_losses.append(train_loss)
        
#         train_rmse, train_mae, train_r2 = evaluate(model, train_loader, epoch, 'train', update_logs_and_charts)
#         train_rmse_scores.append(train_rmse)
#         train_mae_scores.append(train_mae)
#         train_r2_scores.append(train_r2)
        
#         test_rmse, test_mae, test_r2 = evaluate(model, test_loader, epoch, 'test', update_logs_and_charts)
#         test_rmse_scores.append(test_rmse)
#         test_mae_scores.append(test_mae)
#         test_r2_scores.append(test_r2)

#         logging.info(f'Epoch {epoch+1}, Train Loss: {train_loss:.4f}, Train RMSE: {train_rmse:.4f}, Test RMSE: {test_rmse:.4f}, Train MAE: {train_mae:.4f}, Test MAE: {test_mae:.4f}, Train R²: {train_r2:.4f}, Test R²: {test_r2:.4f}')

#         scheduler.step(train_loss)

#         # Save checkpoint
#         save_checkpoint(epoch, model, optimizer, scheduler, train_losses, train_rmse_scores, test_rmse_scores, train_mae_scores, test_mae_scores, train_r2_scores, test_r2_scores, checkpoint_path)

#         # Optionally update logs and charts after each epoch
#         if update_logs_and_charts:
#             # Save the plots
#             save_plots(train_losses, train_rmse_scores, test_rmse_scores, train_mae_scores, test_mae_scores, train_r2_scores, test_r2_scores)

#     # Always update logs and charts at the end of training
#     if not update_logs_and_charts:
#         save_plots(train_losses, train_rmse_scores, test_rmse_scores, train_mae_scores, test_mae_scores, train_r2_scores, test_r2_scores)

#     # Save the model at the end of training
#     torch.save(model.state_dict(), os.path.join('Graphs/Graph110', 'best_model.pt'))

#     return train_losses, train_rmse_scores, test_rmse_scores, train_mae_scores, test_mae_scores, train_r2_scores, test_r2_scores

def load_tags(tags_file):
    """Function to load the tags for each graph."""
    tags_df = pd.read_csv(tags_file)
    tags_dict = pd.Series(tags_df['tag'].values, index=tags_df['graph_index']).to_dict()  # Create a mapping from graph_index to tag
    return tags_dict

# Training function
def train(model, train_loader, test_loader, criterion, optimizer, scheduler, num_epochs, checkpoint_path, update_logs_and_charts):
    # Load tags for train and test data
    tags_train = load_tags('Graphs/Graph110/train_tags.csv')
    tags_test = load_tags('Graphs/Graph110/test_tags.csv')

    # Load from the checkpoint if it exists
    start_epoch, train_losses, train_rmse_scores, test_rmse_scores, train_mae_scores, test_mae_scores, train_r2_scores, test_r2_scores = load_checkpoint(checkpoint_path, model, optimizer, scheduler)

    for epoch in range(start_epoch, num_epochs):
        model.train()
        total_loss = 0

        # Training loop
        for data in train_loader:
            optimizer.zero_grad()

            # Forward pass
            output = model(data).view(-1)  # Flatten the output

            # Get the graph index and retrieve the corresponding tag from tags_train
            graph_index = int(data.batch[0])  # Assuming batch[0] contains the graph_index
            target_tag = tags_train.get(graph_index, None)

            if target_tag is None:
                raise ValueError(f"Tag not found for graph index {graph_index}")

            # Convert the target tag to a tensor
            target_tag_tensor = torch.tensor([target_tag], dtype=torch.float).to(output.device)

            # Compute loss
            loss = criterion(output, target_tag_tensor)
            loss.backward()

            optimizer.step()
            total_loss += loss.item() * data.num_graphs

        train_loss = total_loss / len(train_loader.dataset)
        train_losses.append(train_loss)

        # Evaluate model on train and test sets
        train_rmse, train_mae, train_r2 = evaluate(model, train_loader, epoch, 'train', update_logs_and_charts, tags_train)
        train_rmse_scores.append(train_rmse)
        train_mae_scores.append(train_mae)
        train_r2_scores.append(train_r2)
        
        test_rmse, test_mae, test_r2 = evaluate(model, test_loader, epoch, 'test', update_logs_and_charts, tags_test)
        test_rmse_scores.append(test_rmse)
        test_mae_scores.append(test_mae)
        test_r2_scores.append(test_r2)

        logging.info(f'Epoch {epoch+1}, Train Loss: {train_loss:.4f}, Train RMSE: {train_rmse:.4f}, Test RMSE: {test_rmse:.4f}, Train MAE: {train_mae:.4f}, Test MAE: {test_mae:.4f}, Train R²: {train_r2:.4f}, Test R²: {test_r2:.4f}')

        # Adjust the learning rate based on the scheduler
        scheduler.step(train_loss)

        # Save checkpoint
        save_checkpoint(epoch, model, optimizer, scheduler, train_losses, train_rmse_scores, test_rmse_scores, train_mae_scores, test_mae_scores, train_r2_scores, test_r2_scores, checkpoint_path)

        # Optionally update logs and charts after each epoch
        if update_logs_and_charts:
            save_plots(train_losses, train_rmse_scores, test_rmse_scores, train_mae_scores, test_mae_scores, train_r2_scores, test_r2_scores)

    # Always update logs and charts at the end of training
    if not update_logs_and_charts:
        save_plots(train_losses, train_rmse_scores, test_rmse_scores, train_mae_scores, test_mae_scores, train_r2_scores, test_r2_scores)

    # Save the model at the end of training
    torch.save(model.state_dict(), os.path.join('Graphs/Graph110', 'best_model.pt'))

    return train_losses, train_rmse_scores, test_rmse_scores, train_mae_scores, test_mae_scores, train_r2_scores, test_r2_scores

# Updated evaluate function to use tags
def evaluate(model, loader, epoch, phase, update_logs_and_charts, tags_dict):
    """Evaluates the model."""
    model.eval()
    targets = []
    predictions = []
    total_loss = 0

    with torch.no_grad():
        for data in loader:
            output = model(data).view(-1)  # Flatten the output

            # Get graph index and the corresponding tag
            graph_index = int(data.batch[0])
            target_tag = tags_dict.get(graph_index, None)

            if target_tag is None:
                raise ValueError(f"Tag not found for graph index {graph_index}")

            target_tag_tensor = torch.tensor([target_tag], dtype=torch.float).to(output.device)

            predictions.append(output.item())
            targets.append(target_tag_tensor.item())

            # Compute the loss
            loss = criterion(output, target_tag_tensor)
            total_loss += loss.item() * data.num_graphs

    # Compute evaluation metrics
    mse_score = mean_squared_error(targets, predictions)
    rmse_score = np.sqrt(mse_score)
    mae_score = mean_absolute_error(targets, predictions)
    r2 = r2_score(targets, predictions)

    if update_logs_and_charts:
        log_predictions(predictions, targets, epoch, phase)

    return rmse_score, mae_score, r2

def save_plots(train_losses, train_rmse_scores, test_rmse_scores, train_mae_scores, test_mae_scores, train_r2_scores, test_r2_scores):
    plot_dir = 'Graphs/Graph110'
    if not os.path.exists(plot_dir):
        os.makedirs(plot_dir)

    plt.figure()
    plt.plot(train_losses, label='Train Loss')
    plt.xlabel('Epoch')
    plt.ylabel('Loss')
    plt.legend()
    plt.savefig(os.path.join(plot_dir, 'loss_chart.png'))
    plt.close()

    plt.figure()
    plt.plot(train_rmse_scores, label='Train RMSE')
    plt.plot(test_rmse_scores, label='Test RMSE')
    plt.xlabel('Epoch')
    plt.ylabel('RMSE')
    plt.legend()
    plt.savefig(os.path.join(plot_dir, 'rmse_chart.png'))
    plt.close()

    plt.figure()
    plt.plot(train_mae_scores, label='Train MAE')
    plt.plot(test_mae_scores, label='Test MAE')
    plt.xlabel('Epoch')
    plt.ylabel('MAE')
    plt.legend()
    plt.savefig(os.path.join(plot_dir, 'mae_chart.png'))
    plt.close()

    plt.figure()
    plt.plot(train_r2_scores, label='Train R²')
    plt.plot(test_r2_scores, label='Test R²')
    plt.xlabel('Epoch')
    plt.ylabel('R² Score')
    plt.legend()
    plt.savefig(os.path.join(plot_dir, 'r2_chart.png'))
    plt.close()

# Evaluation function
# def evaluate(model, loader, epoch, phase, update_logs_and_charts):
#     model.eval()
#     targets = []
#     predictions = []
#     with torch.no_grad():
#         for data in loader:
#             output = model(data).view(-1)  # Flatten the output
#             pred = output
#             targets.extend(data.y.view(-1).tolist())  # Flatten the target
#             predictions.extend(pred.tolist())

#     # Log predictions and targets to a file if updating logs and charts
#     if update_logs_and_charts:
#         log_predictions(predictions, targets, epoch, phase)

#     mse_score = mean_squared_error(targets, predictions)
#     rmse_score = np.sqrt(mse_score)
#     mae_score = mean_absolute_error(targets, predictions)
#     r2 = r2_score(targets, predictions)
#     return rmse_score, mae_score, r2

# Signal handler for graceful termination
def signal_handler(sig, frame):
    print('Graceful termination initiated...')
    save_checkpoint(epoch, model, optimizer, scheduler, train_losses, train_rmse_scores, test_rmse_scores, train_mae_scores, test_mae_scores, train_r2_scores, test_r2_scores, checkpoint_path)
    torch.save(model.state_dict(), os.path.join('Graphs/Graph110', 'best_model.pt'))
    sys.exit(0)

# Register signal handler
signal.signal(signal.SIGINT, signal_handler)

# Define checkpoint path
checkpoint_path = os.path.join('Graphs/Graph110', 'checkpoint.pt')

# Variable to control logging and chart updates
update_logs_and_charts = False  # Set to False to update only at the end

# Train the model
train_losses, train_rmse_scores, test_rmse_scores, train_mae_scores, test_mae_scores, train_r2_scores, test_r2_scores = train(model, train_loader, test_loader, criterion, optimizer, scheduler, num_epochs, checkpoint_path, update_logs_and_charts)

# Ensure final predictions are logged
if not update_logs_and_charts:
    evaluate(model, train_loader, num_epochs, 'train', True)
    evaluate(model, test_loader, num_epochs, 'test', True)
