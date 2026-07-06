import sacrebleu
from datasets import load_from_disk
from transformers import BartTokenizer, BartForConditionalGeneration
from bert_score import score as bert_score
import torch
from rouge import Rouge
import datetime
import time
import warnings

# Suppress specific warnings from transformers
warnings.filterwarnings("ignore", category=UserWarning, module="transformers")

# Load tokenizer and model
tokenizer = BartTokenizer.from_pretrained('./output/fine-tuned-bart')
model = BartForConditionalGeneration.from_pretrained('./output/fine-tuned-bart')
device = 'cuda' if torch.cuda.is_available() else 'cpu'
model.eval().to(device)

# Load the tokenized validation data
validation_data_dir = './output/data/tokenized-bart/validation'
validation_data = load_from_disk(validation_data_dir)

# Prepare lists for decoded questions, reference answers, generated answers, and generation times
questions = []
reference_answers = []
generated_answers = []
generation_times = []

# Print header for response times
print("\nResponse Times for Each Question:\n")
print("=" * 50)

for idx, item in enumerate(validation_data, start=1):
    start_time = time.time()  # Start timer

    # Decode input_ids to get the original question
    question = tokenizer.decode(item['input_ids'], skip_special_tokens=True)
    questions.append(question)

    # Decode labels to get the reference answer
    reference_answer = tokenizer.decode(
        [i for i in item['labels'] if i != -100], skip_special_tokens=True
    )
    reference_answers.append(reference_answer)

    # Prepare input tensors for the model
    inputs = torch.tensor(item['input_ids']).unsqueeze(0).to(device)
    attention_mask = torch.tensor(item['attention_mask']).unsqueeze(0).to(device)

    # Generate answer using the model
    with torch.no_grad():
        outputs = model.generate(
            input_ids=inputs,
            attention_mask=attention_mask,
            max_length=516,
            num_beams=6,
        )

    # Decode the generated answer
    generated_answer = tokenizer.decode(outputs[0], skip_special_tokens=True)
    generated_answers.append(generated_answer)

    end_time = time.time()  # End timer
    generation_time = end_time - start_time
    generation_times.append(generation_time)

    # Print the question and its generation time
    print(f"Question {idx}: {question}")
    print(f"Generation Time: {generation_time:.4f} seconds")
    print("-" * 50)

# Compute BERTScore for generated answers
print("\nComputing BERTScore...")
P, R, F1 = bert_score(generated_answers, reference_answers, lang="en", rescale_with_baseline=True)

# Calculate average BERTScore
average_precision = P.mean().item()
average_recall = R.mean().item()
average_f1 = F1.mean().item()

# Compute ROUGE scores
rouge = Rouge()
rouge_scores = rouge.get_scores(generated_answers, reference_answers, avg=True)

# ---------------------------------------------------------
# COLLECT SAMPLES (with per-sample BLEU & BERT F1) AND SORT
# ---------------------------------------------------------
samples = []
for i in range(len(questions)):
    bert_f1 = F1[i].item()
    bleu_score = sacrebleu.sentence_bleu(generated_answers[i], [reference_answers[i]]).score

    samples.append(
        {
            "index": i + 1,
            "question": questions[i],
            "reference_answer": reference_answers[i],
            "generated_answer": generated_answers[i],
            "bert_f1": bert_f1,
            "bleu_score": bleu_score,
            "generation_time": generation_times[i],
        }
    )

# Sort the samples by BERT F1 in descending order
samples.sort(key=lambda x: x["bert_f1"], reverse=True)

# Calculate the average BLEU across all samples
average_bleu = sum(sample["bleu_score"] for sample in samples) / len(samples)

# Calculate average generation time
average_generation_time = sum(generation_times) / len(generation_times)

# Create evaluation report
timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
output_file = f'evaluation_results_{timestamp}.txt'

with open(output_file, 'w', encoding='utf-8') as f:
    # Write header
    f.write("BART Model Evaluation Results\n")
    f.write("=" * 30 + "\n\n")

    # Write date and time
    f.write(f"Evaluation Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

    # Write individual sample evaluations, sorted by BERT F1
    f.write("Individual Sample Evaluations (sorted by BERTScore F1):\n")
    f.write("=" * 30 + "\n\n")

    for sample in samples:
        f.write(f"Sample {sample['index']}:\n")
        f.write(f"Question: {sample['question']}\n")
        f.write(f"Reference Answer: {sample['reference_answer']}\n")
        f.write(f"Generated Answer: {sample['generated_answer']}\n")
        f.write(f"BERTScore F1: {sample['bert_f1']:.4f}\n")
        f.write(f"BLEU Score: {sample['bleu_score']:.4f}\n")
        f.write(f"Generation Time: {sample['generation_time']:.4f} seconds\n")
        f.write("-" * 50 + "\n\n")

    # Add the overall averages at the end
    f.write("Overall Averages (All Samples):\n")
    f.write("=" * 30 + "\n")
    f.write(f"Average BERTScore Precision: {average_precision:.4f}\n")
    f.write(f"Average BERTScore Recall: {average_recall:.4f}\n")
    f.write(f"Average BERTScore F1: {average_f1:.4f}\n")
    f.write(f"Average BLEU Score: {average_bleu:.4f}\n")
    f.write(f"Average Generation Time: {average_generation_time:.4f} seconds\n\n")

    # Write ROUGE scores
    f.write("ROUGE Scores:\n")
    f.write("=" * 30 + "\n")
    f.write(
        f"ROUGE-1: P={rouge_scores['rouge-1']['p']:.4f}, "
        f"R={rouge_scores['rouge-1']['r']:.4f}, "
        f"F1={rouge_scores['rouge-1']['f']:.4f}\n"
    )
    f.write(
        f"ROUGE-2: P={rouge_scores['rouge-2']['p']:.4f}, "
        f"R={rouge_scores['rouge-2']['r']:.4f}, "
        f"F1={rouge_scores['rouge-2']['f']:.4f}\n"
    )
    f.write(
        f"ROUGE-L: P={rouge_scores['rouge-l']['p']:.4f}, "
        f"R={rouge_scores['rouge-l']['r']:.4f}, "
        f"F1={rouge_scores['rouge-l']['f']:.4f}\n\n"
    )

    # Write score explanations
    f.write("Score Explanations:\n")
    f.write("=" * 30 + "\n\n")
    f.write(
        """
ROUGE-1: Measures single word overlap between generated and reference text
ROUGE-2: Measures two-word (bigram) overlap
ROUGE-L: Measures the longest matching word sequence
BERTScore: Measures semantic similarity using contextual embeddings
BLEU Score: Measures n-gram precision with length penalty
Generation Time: Time taken to generate the answer for each question
        """
    )

# Print average generation time
print("\nAverage Generation Time: {:.4f} seconds".format(average_generation_time))
print(f"\nEvaluation results have been saved to: {output_file}")
