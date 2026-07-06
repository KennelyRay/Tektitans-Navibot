import subprocess
from torch.optim import AdamW
from transformers import (
    BartForConditionalGeneration,
    BartTokenizer,
    Trainer,
    TrainingArguments,
    TrainerCallback,
    EarlyStoppingCallback,
    get_cosine_schedule_with_warmup,
    BartConfig,
    DataCollatorForSeq2Seq
)
from datasets import load_dataset, DatasetDict
import torch
import random
import numpy as np
from transformers import set_seed
import logging
import warnings

# Suppress specific warnings if necessary (optional)
warnings.filterwarnings("ignore", category=UserWarning, module="transformers")
warnings.filterwarnings("ignore", category=FutureWarning, module="torch")

logging.basicConfig(
    filename='training_output.log',  # File to save logs
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger()

# Set a random seed for reproducibility
seed = 123
random.seed(seed)
np.random.seed(seed)
torch.manual_seed(seed)
set_seed(seed)

# Use CUDA if available
if torch.cuda.is_available():
    torch.cuda.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)

# Verify CUDA availability
logger.info("CUDA available: %s", torch.cuda.is_available())
print("CUDA available:", torch.cuda.is_available())
print("cuDNN enabled:", torch.backends.cudnn.enabled)

# Set device
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Using device: {device}")

# Define constants
MAX_LEN = 300

# Define a callback to log losses
class LogLossesCallback(TrainerCallback):
    def __init__(self):
        self.epochs = []
        self.training_losses = []
        self.validation_losses = []
        self.current_epoch = 0

    def on_log(self, args, state, control, logs=None, **kwargs):
        # This function is called during logging steps
        if logs is not None and state.is_local_process_zero:
            if 'loss' in logs and 'epoch' in logs:
                self.current_epoch = int(logs['epoch'])
                self.training_losses.append((self.current_epoch, logs['loss']))
            if 'eval_loss' in logs and 'epoch' in logs:
                self.current_epoch = int(logs['epoch'])
                self.validation_losses.append((self.current_epoch, logs['eval_loss']))

# Step 1: Load data from JSON
def load_data(train_file, output_dir='./output/data/Batch1_Splits', seed=42):
    # Load the dataset from a JSON file
    print("Loading and processing dataset...")
    data = load_dataset('json', data_files=train_file, split='train')
    data = data.shuffle(seed=seed)

    # First split: 80% train, 20% temporary split
    train_temp_split = data.train_test_split(test_size=0.2, shuffle=True, seed=seed)
    train_data = train_temp_split['train']
    temp_data = train_temp_split['test']

    # Second split: 10% validation and 10% test
    validation_test_split = temp_data.train_test_split(test_size=0.5, shuffle=True, seed=seed)
    validation_data = validation_test_split['train']
    test_data = validation_test_split['test']

    # Create DatasetDict with all three splits
    data_splits = DatasetDict({
        'train': train_data,
        'validation': validation_data,
        'test': test_data
    })

    # Save the dataset splits to disk
    data_splits.save_to_disk(output_dir)

    return data_splits

# Step 2: Tokenization
def tokenize(samples):
    input_encodings = tokenizer(
        samples['question'],
        truncation=True,
        max_length=MAX_LEN,
        padding=False
    )

    labels = tokenizer(
        text_target=samples['answer'],
        truncation=True,
        max_length=MAX_LEN,
        padding=False,
    )

    input_encodings['labels'] = labels['input_ids']
    return input_encodings

# Step 3: Preprocess the dataset and apply tokenization
def preprocess_data(data_splits, tokenizer):
    tokenized_data = data_splits.map(
        tokenize,
        batched=True,
        remove_columns=['question', 'answer']
    )

    tokenized_data.save_to_disk('./output/data/tokenized-bart')
    return tokenized_data

# Step 4: Train the model
def train_model():
    global tokenizer  # Declare tokenizer as global to use it in tokenize function

    # Load the tokenizer and add special tokens
    tokenizer = BartTokenizer.from_pretrained('facebook/bart-large')
    special_tokens_list = [
         '<EMAIL>', '</EMAIL>', '<URL>', '</URL>',
        '<STEPS>', '</STEPS>', '<SECTION>', '</SECTION>',
        '<DEPT_CONTACT>', '</DEPT_CONTACT>', '<DEPT_NAME>', '</DEPT_NAME>',
        '<SUBJECT>', '</SUBJECT>'
    ]

    special_tokens_dict = {'additional_special_tokens': special_tokens_list}
    tokenizer.add_special_tokens(special_tokens_dict)

    tokenizer.save_pretrained('./output/fine-tuned-bart')

    # Load or preprocess the dataset
    data_splits = load_data('Data/Batch1_Train.json')  # Change path to your file
    tokenized_datasets = preprocess_data(data_splits, tokenizer)

    # Print special tokens information before training
    print("\n[BEFORE TRAINING] Special Tokens Info:")
    print("Special Tokens Map:", tokenizer.special_tokens_map)
    print("Additional Special Tokens:", tokenizer.additional_special_tokens)
    for token in tokenizer.additional_special_tokens:
        tid = tokenizer.convert_tokens_to_ids(token)
        print(f"Token: {token}, ID: {tid}")

    # Check tokenization with special tokens
    text_with_special = (
        "Please send an email to <EMAIL>admissions@university.edu</EMAIL>. "
        "For steps, check <STEPS>1. Apply online</STEPS> and visit "
        "<URL>http://example.com</URL> or contact <DEPT_CONTACT>Registrar</DEPT_CONTACT>."
    )
    special_tokens = tokenizer.tokenize(text_with_special)
    special_token_ids = tokenizer.convert_tokens_to_ids(special_tokens)

    print("\n[BEFORE TRAINING] Tokenization Check (Text with Special Tokens):")
    print(f"Text: {text_with_special}")
    print("Tokens:", special_tokens)
    print("Token IDs:", special_token_ids)

    # After checking, proceed with model loading and training
    config = BartConfig.from_pretrained('facebook/bart-large')
    config.dropout = 0.25

    model = BartForConditionalGeneration.from_pretrained('facebook/bart-large', config=config)
    model.resize_token_embeddings(len(tokenizer))
    model.to(device)

    training_args = TrainingArguments(
        output_dir="./output",
        overwrite_output_dir=True,
        per_device_train_batch_size=16,
        per_device_eval_batch_size=16,
        num_train_epochs=25,
        learning_rate=2e-5,
        eval_strategy="epoch",
        weight_decay=0.1,
        optim="adamw_torch",
        save_steps=10240,
        save_total_limit=2,
        logging_dir='./logs',
        logging_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model='eval_loss',
        greater_is_better=False,
        max_grad_norm=1.0,
        fp16=True
    )

    no_decay = ["bias", "LayerNorm.weight"]
    optimizer_grouped_parameters = [
        {
            "params": [p for n, p in model.named_parameters() if not any(nd in n for nd in no_decay)],
            "weight_decay": training_args.weight_decay,
        },
        {
            "params": [p for n, p in model.named_parameters() if any(nd in n for nd in no_decay)],
            "weight_decay": 0.0,
        },
    ]

    optimizer = AdamW(optimizer_grouped_parameters, lr=training_args.learning_rate)

    # Calculate total training steps
    num_training_steps = (
        int(len(tokenized_datasets['train']) / training_args.per_device_train_batch_size) *
        training_args.num_train_epochs
    )
    total_steps = num_training_steps
    warmup_steps = int(0.1 * total_steps)

    scheduler = get_cosine_schedule_with_warmup(
        optimizer=optimizer,
        num_warmup_steps=warmup_steps,
        num_training_steps=num_training_steps
    )

    data_collator = DataCollatorForSeq2Seq(tokenizer=tokenizer, model=model)

    log_losses_callback = LogLossesCallback()
    early_stopping_callback = EarlyStoppingCallback(
        early_stopping_patience=3,
        early_stopping_threshold=0.0001
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_datasets['train'],
        eval_dataset=tokenized_datasets['validation'],
        tokenizer=tokenizer,
        data_collator=data_collator,
        callbacks=[log_losses_callback, early_stopping_callback],
        optimizers=(optimizer, scheduler)
    )

    # Now that we've seen the tokens, train the model
    trainer.train()

    # Save the model and tokenizer
    model.save_pretrained('./output/fine-tuned-bart')
    tokenizer.save_pretrained('./output/fine-tuned-bart')

    # Prepare the data for printing after training
    epochs = []
    training_losses = {}
    validation_losses = {}

    for epoch, loss in log_losses_callback.training_losses:
        training_losses[epoch] = loss

    for epoch, loss in log_losses_callback.validation_losses:
        validation_losses[epoch] = loss

    all_epochs = sorted(set(list(training_losses.keys()) + list(validation_losses.keys())))

    # Print the losses
    print("\nEpoch\tTraining Loss\tValidation Loss")
    for epoch in all_epochs:
        train_loss = training_losses.get(epoch, "N/A")
        val_loss = validation_losses.get(epoch, "N/A")

        if isinstance(train_loss, (int, float)):
            train_loss = f"{train_loss:.6f}"
        if isinstance(val_loss, (int, float)):
            val_loss = f"{val_loss:.6f}"

        print(f"{epoch}\t{train_loss}\t{val_loss}")

    # Print special tokens after training (just for confirmation)
    print("\nSpecial Tokens After Training:")
    print(tokenizer.special_tokens_map)
    print("\nAdditional Special Tokens:")
    print(tokenizer.additional_special_tokens)
    for token in tokenizer.additional_special_tokens:
        token_id = tokenizer.convert_tokens_to_ids(token)
        print(f"Token: {token}, ID: {token_id}")

    # Check tokenization again after training (optional)
    sample_text = "question: What is the admission process?"
    tokens = tokenizer.tokenize(sample_text)
    token_ids = tokenizer.convert_tokens_to_ids(tokens)

    print("\nTokenization Result After Training:")
    print(f"Tokens: {tokens}")
    print(f"Token IDs: {token_ids}")


if __name__ == "__main__":
    train_model()
    # Run the second Python script if needed
    subprocess.run(["python", "BertScore_Bart.py"])
