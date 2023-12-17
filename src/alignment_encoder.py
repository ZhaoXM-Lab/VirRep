import torch
from torch import nn


class SkipGram(nn.Module):
    
    def __init__(self, k, embedding_size):
        super(SkipGram, self).__init__()
        
        self.k = k
        self.kmer_size = 4**k
        self.embedding_size = embedding_size
        
        self.embedding_in = nn.Embedding(self.kmer_size, embedding_size, sparse=True)
        self.embedding_out = nn.Embedding(self.kmer_size, embedding_size, sparse=True)
        
        self.embedding_in.weight.data.uniform_(-1, 1)
        self.embedding_out.weight.data.uniform_(-1, 1)
        
    def forward(self, center_word, target_word):
        
        center_emb = self.embedding_in(center_word)
        target_emb = self.embedding_out(target_word)
        
        center_trans = center_emb.transpose(1, 2)
        logit = torch.bmm(target_emb, center_trans)
        logit = logit.squeeze(dim=2)
        
        return logit
    
    
class KmerEmbedding(nn.Module):
    
    def __init__(self, config):
        super(KmerEmbedding, self).__init__()
        
        self.kmer_embedding = nn.Embedding(config.vocab_size,
                                           config.embed_size,
                                           padding_idx=0)
        self.LayerNorm = nn.LayerNorm(config.embed_size)
        self.dropout = nn.Dropout(config.dropout_rate)
        
    def forward(self, input_ids):
        return self.dropout(self.LayerNorm(self.kmer_embedding(input_ids)))
    

class LSTMEncoder(nn.Module):
    
    def __init__(self, config):
        super(LSTMEncoder, self).__init__()
        direction = 2 if config.bidirectional else 1
        
        self.lstm = nn.LSTM(input_size=config.embed_size,
                            hidden_size=config.hidden_size,
                            num_layers=config.num_lstm_layers,
                            batch_first=True,
                            dropout=config.dropout_rate,
                            bidirectional=config.bidirectional)
        
        self.LayerNorm = nn.LayerNorm(direction*config.hidden_size)
        self.dropout = nn.Dropout(config.dropout_rate)
        
    def forward(self, embeddings):
        
        out, (hn, cn) = self.lstm(embeddings)
        seqembed = out.mean(dim=1)
        seqembed = self.dropout(self.LayerNorm(seqembed))
        
        return seqembed
    
    
class Pooler(nn.Module):
    
    def __init__(self, config):
        super(Pooler, self).__init__()
        direction = 2 if config.bidirectional else 1
        
        self.linear = nn.Linear(direction*config.hidden_size, config.hidden_size)
        self.LayerNorm = nn.LayerNorm(config.hidden_size)
        self.Tanh = nn.Tanh()
        self.dropout = nn.Dropout(config.dropout_rate)
        
    def forward(self, hidden_states):
        return self.dropout(self.Tanh(self.LayerNorm(self.linear(hidden_states))))
    
    
class AERegressor(nn.Module):
    
    def __init__(self, config):
        super(AERegressor, self).__init__()
        
        self.linear = nn.Linear(config.hidden_size, 1)
        self.sigmoid = nn.Sigmoid()
        
    def forward(self, hidden_states):
        return self.sigmoid(self.linear(hidden_states))
    
    
class AEForSimPred(nn.Module):
    
    def __init__(self, config):
        super(AEForSimPred, self).__init__()

        self.embedding = KmerEmbedding(config)
        self.encoder = LSTMEncoder(config)
        self.pooler = Pooler(config)
        self.regressor = AERegressor(config)
    
    
    def forward(self, input_fw, input_rc):
        embed_fw = self.embedding(input_fw)
        embed_rc = self.embedding(input_rc)
        
        # out_fw, (hn_fw, cn_fw) = self.encoder(embed_fw)
        # out_rc, (hn_rc, cn_rc) = self.encoder(embed_rc)
        
        # seqembed_fw = out_fw.mean(dim=1)
        # seqembed_rc = out_rc.mean(dim=1)
        
        # seqembed_fw = self.ln_encoder(seqembed_fw)
        # seqembed_rc = self.ln_encoder(seqembed_rc)
        
        seqembed_fw = self.encoder(embed_fw)
        seqembed_rc = self.encoder(embed_rc)
        
        seqembed_fw = self.pooler(seqembed_fw)
        seqembed_rc = self.pooler(seqembed_rc)
        
        output_fw = self.regressor(seqembed_fw)
        output_rc = self.regressor(seqembed_rc)
        output = (output_fw + output_rc) / 2
        
        return output


class AlignmentEncoder(nn.Module):
    
    def __init__(self, config):
        super(AlignmentEncoder, self).__init__()
        # direction = 2 if config.bidirectional else 1
        
        self.embedding = KmerEmbedding(config)
        
        # self.encoder = nn.LSTM(input_size=config.embed_size,
        #                        hidden_size=config.hidden_size,
        #                        num_layers=config.num_lstm_layers,
        #                        batch_first=True,
        #                        dropout=config.dropout_rate,
        #                        bidirectional=config.bidirectional)
        
        # self.ln_encoder = nn.Sequential()
        # self.ln_encoder.add_module('ln', nn.LayerNorm(
        #     direction*config.hidden_size))
        # self.ln_encoder.add_module('dropout', nn.Dropout(config.dropout_rate))
        
        self.encoder = LSTMEncoder(config)
        self.pooler = Pooler(config)
        
        
    def forward(self, input_fw, input_rc):
        
        embed_fw = self.embedding(input_fw)
        embed_rc = self.embedding(input_rc)
        
        # out_fw, (hn_fw, cn_fw) = self.encoder(embed_fw)
        # out_rc, (hn_rc, cn_rc) = self.encoder(embed_rc)
        
        # seqembed_fw = out_fw.mean(dim=1)
        # seqembed_rc = out_rc.mean(dim=1)
        
        # seqembed_fw = self.ln_encoder(seqembed_fw)
        # seqembed_rc = self.ln_encoder(seqembed_rc)
        
        seqembed_fw = self.encoder(embed_fw)
        seqembed_rc = self.encoder(embed_rc)
        
        pooled_output_fw = self.pooler(seqembed_fw)
        pooled_output_rc = self.pooler(seqembed_rc)
        
        return pooled_output_fw, pooled_output_rc
    
    def count_params(self):
        return sum(p.numel() for p in self.parameters() if p.requires_grad)
    

class AlnConfig():
    
    def __init__(self, vocab_size, embed_size, hidden_size,
                 num_lstm_layers, bidirectional, dropout_rate=0.1):
        
        self.vocab_size = vocab_size
        self.embed_size = embed_size
        self.hidden_size = hidden_size
        self.num_lstm_layers = num_lstm_layers
        self.bidirectional = bidirectional
        self.dropout_rate = dropout_rate