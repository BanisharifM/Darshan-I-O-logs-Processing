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
from sklearn.metrics import mean_squared_error, accuracy_score
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score
import numpy as np

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Define the enhanced GNN model with more layers and units
class EnhancedGNN(torch.nn.Module):
    def __init__(self, num_node_features, num_classes):
        super(EnhancedGNN, self).__init__()
        self.conv1 = GCNConv(num_node_features, 64)
        self.conv2 = GCNConv(64, 128)
        self.conv3 = GCNConv(128, 64)
        self.conv4 = GCNConv(64, num_classes)
        self.dropout = torch.nn.Dropout(p=0.5)

    def forward(self, data):
        x, edge_index, batch = data.x, data.edge_index, data.batch
        x = self.conv1(x, edge_index)
        x = F.relu(x)
        x = self.dropout(x)
        x = self.conv2(x, edge_index)
        x = F.relu(x)
        x = self.dropout(x)
        x = self.conv3(x, edge_index)
        x = F.relu(x)
        x = self.dropout(x)
        x = self.conv4(x, edge_index)
        # Pooling layer to get a graph-level output
        x = global_mean_pool(x, batch)
        return F.log_softmax(x, dim=1)

# Load data from CSV files and create PyTorch Geometric Data objects
def load_data(file_path):
    df = pd.read_csv(file_path)
    graphs = []
    scaler = StandardScaler()
    for graph_index in df['graph_index'].unique():
        graph_df = df[df['graph_index'] == graph_index]
        x = torch.tensor(scaler.fit_transform(graph_df[['node_value']].values), dtype=torch.float)
        edge_index = torch.tensor([[i, 0] for i in range(1, len(graph_df))], dtype=torch.long).t().contiguous()
        # y = torch.tensor([graph_df['tag_value'].iloc[0]], dtype=torch.long)
        y_value = int(graph_df['tag_value'].iloc[0])
        y = torch.tensor([y_value], dtype=torch.long)

        data = Data(x=x, edge_index=edge_index, y=y)
        graphs.append(data)
    return graphs

# Define paths to the data files
train_file_path = "Graphs/Graph47/train_graphs.csv"
test_file_path = "Graphs/Graph47/test_graphs.csv"

# Load the data
train_data = load_data(train_file_path)
test_data = load_data(test_file_path)

# Hyperparameters
num_epochs = 200
batch_size = 64
learning_rate = 0.001
weight_decay = 1e-4

# Create data loader
train_loader = DataLoader(train_data, batch_size=batch_size, shuffle=True)
test_loader = DataLoader(test_data, batch_size=batch_size, shuffle=False)

# Initialize the model, optimizer, and loss function
num_node_features = 1
num_classes = len(pd.read_csv(train_file_path)['tag_value'].unique())
model = EnhancedGNN(num_node_features, num_classes)
optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate, weight_decay=weight_decay)
scheduler = ReduceLROnPlateau(optimizer, 'min', factor=0.5, patience=10, min_lr=1e-6)
criterion = torch.nn.CrossEntropyLoss()

# Checkpointing function
def save_checkpoint(epoch, model, optimizer, scheduler, train_losses, train_rmse_scores, test_rmse_scores, train_accuracies, test_accuracies, checkpoint_path):
    torch.save({
        'epoch': epoch,
        'model_state_dict': model.state_dict(),
        'optimizer_state_dict': optimizer.state_dict(),
        'scheduler_state_dict': scheduler.state_dict(),
        'train_losses': train_losses,
        'train_rmse_scores': train_rmse_scores,
        'test_rmse_scores': test_rmse_scores,
        'train_accuracies': train_accuracies,
        'test_accuracies': test_accuracies,
    }, checkpoint_path)

def load_checkpoint(checkpoint_path, model, optimizer, scheduler):
    if os.path.exists(checkpoint_path):
        checkpoint = torch.load(checkpoint_path)
        model.load_state_dict(checkpoint['model_state_dict'])
        optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
        scheduler.load_state_dict(checkpoint['scheduler_state_dict'])
        epoch = checkpoint['epoch']
        train_losses = checkpoint['train_losses']
        train_rmse_scores = checkpoint['train_rmse_scores']
        test_rmse_scores = checkpoint['test_rmse_scores']
        train_accuracies = checkpoint['train_accuracies']
        test_accuracies = checkpoint['test_accuracies']
        logging.info(f'Loaded checkpoint from {checkpoint_path}, starting at epoch {epoch + 1}')
        return epoch, train_losses, train_rmse_scores, test_rmse_scores, train_accuracies, test_accuracies
    else:
        return 0, [], [], [], [], []

# Training function
def train(model, train_loader, test_loader, criterion, optimizer, scheduler, num_epochs, checkpoint_path):
    start_epoch, train_losses, train_rmse_scores, test_rmse_scores, train_accuracies, test_accuracies = load_checkpoint(checkpoint_path, model, optimizer, scheduler)

    for epoch in range(start_epoch, num_epochs):
        model.train()
        total_loss = 0
        correct_train = 0
        for data in train_loader:
            optimizer.zero_grad()
            output = model(data)
            loss = criterion(output, data.y)
            loss.backward()
            optimizer.step()
            total_loss += loss.item() * data.num_graphs
            pred = output.argmax(dim=1)
            correct_train += (pred == data.y).sum().item()

        train_loss = total_loss / len(train_loader.dataset)
        train_losses.append(train_loss)
        
        train_rmse, train_acc = evaluate(model, train_loader)
        train_rmse_scores.append(train_rmse)
        train_accuracies.append(train_acc)
        
        test_rmse, test_acc = evaluate(model, test_loader)
        test_rmse_scores.append(test_rmse)
        test_accuracies.append(test_acc)

        logging.info(f'Epoch {epoch+1}, Train Loss: {train_loss:.4f}, Train RMSE: {train_rmse:.4f}, Test RMSE: {test_rmse:.4f}, Train Acc: {train_acc:.4f}, Test Acc: {test_acc:.4f}')

        scheduler.step(train_loss)

        # Save checkpoint
        save_checkpoint(epoch, model, optimizer, scheduler, train_losses, train_rmse_scores, test_rmse_scores, train_accuracies, test_accuracies, checkpoint_path)

        # Save the model at the end of each epoch
        torch.save(model.state_dict(), os.path.join('Graphs/Graph47', 'best_model.pt'))

    return train_losses, train_rmse_scores, test_rmse_scores, train_accuracies, test_accuracies

# Evaluation function
def evaluate(model, loader):
    model.eval()
    targets = []
    predictions = []
    with torch.no_grad():
        for data in loader:
            output = model(data)
            pred = output.argmax(dim=1)
            targets.extend(data.y.tolist())
            predictions.extend(pred.tolist())

    mse_score = mean_squared_error(targets, predictions)
    rmse_score = np.sqrt(mse_score)
    accuracy = accuracy_score(targets, predictions)
    return rmse_score, accuracy

# Define checkpoint path
checkpoint_path = os.path.join('Graphs/Graph47', 'checkpoint.pt')

# Train the model
train_losses, train_rmse_scores, test_rmse_scores, train_accuracies, test_accuracies = train(model, train_loader, test_loader, criterion, optimizer, scheduler, num_epochs, checkpoint_path)

# Plot and save the loss and accuracy charts
plt.figure()
plt.plot(train_losses, label='Train Loss')
plt.xlabel('Epoch')
plt.ylabel('Loss')
plt.legend()
plt.savefig(os.path.join('Graphs/Graph47', 'loss_chart.png'))

plt.figure()
plt.plot(train_rmse_scores, label='Train RMSE')
plt.plot(test_rmse_scores, label='Test RMSE')
plt.xlabel('Epoch')
plt.ylabel('RMSE')
plt.legend()
plt.savefig(os.path.join('Graphs/Graph47', 'rmse_chart.png'))

plt.figure()
plt.plot(train_accuracies, label='Train Accuracy')
plt.plot(test_accuracies, label='Test Accuracy')
plt.xlabel('Epoch')
plt.ylabel('Accuracy')
plt.legend()
plt.savefig(os.path.join('Graphs/Graph47', 'accuracy_chart.png'))
