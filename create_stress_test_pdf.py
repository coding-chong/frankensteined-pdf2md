#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Create a 10-page test PDF with images for stress testing."""

import fitz  # PyMuPDF
from pathlib import Path
import math


def create_test_image(width: int = 400, height: int = 300, pattern: str = "grid") -> bytes:
    """Create a test image as PNG bytes."""
    import io
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new('RGB', (width, height), color='white')
    draw = ImageDraw.Draw(img)

    if pattern == "grid":
        # Draw a grid pattern
        for i in range(0, width, 50):
            draw.line([(i, 0), (i, height)], fill='lightgray', width=1)
        for i in range(0, height, 50):
            draw.line([(0, i), (width, i)], fill='lightgray', width=1)
        # Draw some shapes
        draw.rectangle([50, 50, 150, 150], fill='lightblue', outline='blue')
        draw.ellipse([200, 50, 350, 180], fill='lightgreen', outline='green')
        draw.polygon([(100, 200), (50, 280), (150, 280)], fill='lightyellow', outline='orange')

    elif pattern == "chart":
        # Draw a simple bar chart
        bars = [80, 120, 200, 150, 180, 90, 160]
        bar_width = 40
        spacing = 10
        x_start = 30
        for i, height_val in enumerate(bars):
            x = x_start + i * (bar_width + spacing)
            draw.rectangle([x, height - 50 - height_val, x + bar_width, height - 50],
                          fill='steelblue', outline='navy')
        # X axis
        draw.line([(20, height - 50), (width - 20, height - 50)], fill='black', width=2)
        draw.text((width//2 - 30, 10), "Bar Chart", fill='black')

    elif pattern == "circuit":
        # Draw a simple circuit diagram
        # Resistor symbol
        draw.line([(50, 100), (100, 100)], fill='black', width=2)
        for i in range(5):
            x = 100 + i * 20
            draw.line([(x, 100), (x + 10, 80)], fill='black', width=2)
            draw.line([(x + 10, 80), (x + 20, 100)], fill='black', width=2)
        draw.line([(200, 100), (250, 100)], fill='black', width=2)
        draw.text((100, 120), "R1 = 10kΩ", fill='black')

        # Capacitor symbol
        draw.line([(100, 180), (170, 180)], fill='black', width=2)
        draw.line([(170, 160), (170, 200)], fill='black', width=2)
        draw.line([(190, 160), (190, 200)], fill='black', width=2)
        draw.line([(190, 180), (260, 180)], fill='black', width=2)
        draw.text((200, 200), "C1 = 100nF", fill='black')

    elif pattern == "diagram":
        # Draw a block diagram
        blocks = [
            (50, 50, 100, 60, "CPU"),
            (200, 50, 100, 60, "Memory"),
            (350, 50, 100, 60, "I/O"),
            (125, 150, 100, 60, "Bus"),
        ]
        for x, y, w, h, label in blocks:
            draw.rectangle([x, y, x + w, y + h], fill='lightyellow', outline='black', width=2)
            # Center text
            text_bbox = draw.textbbox((0, 0), label)
            text_w = text_bbox[2] - text_bbox[0]
            draw.text((x + (w - text_w) // 2, y + 20), label, fill='black')

        # Draw connections
        draw.line([(100, 80), (125, 80)], fill='black', width=2)
        draw.line([(175, 80), (200, 80)], fill='black', width=2)
        draw.line([(300, 80), (350, 80)], fill='black', width=2)

    elif pattern == "waveform":
        # Draw a waveform
        import math
        draw.line([(20, height // 2), (width - 20, height // 2)], fill='gray', width=1)

        points = []
        for x in range(20, width - 20):
            y = height // 2 + int(50 * math.sin((x - 20) * 0.1))
            points.append((x, y))

        draw.line(points, fill='blue', width=2)
        draw.text((width // 2 - 40, 10), "Sine Wave", fill='black')

    else:  # pattern == "mixed"
        # Mixed content
        draw.rectangle([20, 20, 180, 140], fill='#f0f0f0', outline='gray')
        draw.text((30, 30), "Block A", fill='black')

        draw.ellipse([220, 20, 380, 140], fill='#e0ffe0', outline='green')
        draw.text((270, 70), "Block B", fill='green')

        draw.line([(20, 180), (380, 180)], fill='blue', width=3)
        draw.text((150, 200), "Signal Line", fill='blue')

    # Add label
    draw.text((width - 100, height - 20), f"Test Image", fill='gray')

    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def create_stress_test_pdf(output_path: Path, num_pages: int = 10):
    """Create a multi-page PDF with text, code, tables, and images."""

    doc = fitz.open()

    # Page content templates
    page_contents = [
        {
            "title": "Chapter 1: Introduction to OCR Flow",
            "text": """This document is a comprehensive test file for the OCR Flow pipeline.

OCR Flow is a command-line tool designed to convert PDF documents, particularly chip manuals
and technical documentation, into AI-readable Markdown format.

Key Features:
• PDF type detection (text vs scanned)
• Multi-language OCR support via UMI OCR
• PDF translation using BabelDOC
• Document compression with Ghostscript
• Markdown conversion via MinerU API
• Format fixing and image localization

This test document contains various elements including:
- Text paragraphs
- Code blocks
- Tables
- Diagrams and images
- Mathematical formulas

The goal is to verify that the entire pipeline works correctly on a realistic document.""",
            "image_pattern": "diagram",
            "code": """# Example: Initialize OCR Flow
from ocr_flow import Pipeline, Config

config = Config.load()
pipeline = Pipeline(config, verbose=True)

result = pipeline.run(
    input_pdf="datasheet.pdf",
    output_dir="./output",
    pdf_type="auto",
    language="en",
    translate=True
)
print(f"Output: {result}")""",
        },
        {
            "title": "Chapter 2: System Architecture",
            "text": """The OCR Flow system is built around a pipeline architecture. Each processing step
is an independent module that can be enabled or disabled based on requirements.

Processing Steps:
1. PDF Type Detection - Determines if the PDF contains extractable text
2. OCR Processing - Uses UMI OCR for scanned documents
3. Translation - Optional BabelDOC integration for multilingual support
4. PDF Splitting - Divides large documents into manageable chunks
5. Compression - Reduces file size with Ghostscript
6. Markdown Conversion - Extracts structured content via MinerU API
7. Format Fixing - Applies formatting corrections
8. Image Download - Localizes remote images

State Management:
The pipeline maintains state in .state.json files, allowing for resume/retry
functionality in case of failures.""",
            "image_pattern": "circuit",
            "code": """# Pipeline state management
class State:
    def __init__(self, source_path: Path, options: Dict):
        self.source_path = str(source_path)
        self.options = options
        self.steps: Dict[str, StepStatus] = {}

    def update_step(self, step_name: str, status: str):
        self.steps[step_name] = StepStatus(status=status)
        self.save()

    def is_completed(self) -> bool:
        return all(s.status in ('completed', 'skipped')
                   for s in self.steps.values())""",
        },
        {
            "title": "Chapter 3: Configuration",
            "text": """OCR Flow uses a TOML configuration file located at ~/.ocr-flow/config.toml.

The configuration includes:

[mineru]
API token for MinerU cloud service

[babeldoc]
Path to BabelDOC installation (optional)
Translation language settings
OpenAI-compatible API configuration

[umiocr]
OCR service URL (default: http://127.0.0.1:1224)
Language configuration file

[compress]
Ghostscript path (auto-detected if not specified)
Compression quality preset

Configuration can be set interactively using:
    ocr-flow config

Or by manually editing the configuration file.""",
            "image_pattern": "grid",
            "code": """# config.toml example
[babeldoc]
path = "../BabelDOC"
lang_in = "en-US"
lang_out = "zh-CN"
openai = true
openai_model = "qwen3.5-flash"
openai_base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
openai_api_key = "sk-xxx"

[umiocr]
url = "http://127.0.0.1:1224"
language = "models/config_en.txt"

[mineru]
api_token = "your-token-here" """,
        },
        {
            "title": "Chapter 4: Memory Map Reference",
            "text": """This section demonstrates table handling with a typical memory map.

Memory Organization:
The device has a 4GB address space divided into several regions. The following
table shows the memory map for the peripheral bus:

| Address Range    | Size   | Peripheral      | Description          |
|------------------|--------|-----------------|----------------------|
| 0x4000_0000      | 64KB   | GPIO            | General Purpose I/O  |
| 0x4001_0000      | 32KB   | UART            | Serial Interface     |
| 0x4002_0000      | 16KB   | SPI             | SPI Controller       |
| 0x4003_0000      | 16KB   | I2C             | I2C Controller       |
| 0x4004_0000      | 64KB   | Timer           | General Timer        |
| 0x4005_0000      | 32KB   | ADC             | Analog to Digital    |
| 0x5000_0000      | 1MB    | Flash Controller| Internal Flash       |
| 0x6000_0000      | 256KB  | SRAM            | Internal RAM         |

Access permissions vary by region. Some regions are read-only, others support
full read/write access.""",
            "image_pattern": "chart",
            "code": """// Memory map access example
#define GPIO_BASE       0x40000000
#define UART_BASE       0x40010000
#define SPI_BASE        0x40020000
#define I2C_BASE        0x40030000

typedef struct {
    volatile uint32_t MODER;
    volatile uint32_t OTYPER;
    volatile uint32_t OSPEEDR;
    volatile uint32_t PUPDR;
    volatile uint32_t IDR;
    volatile uint32_t ODR;
} GPIO_TypeDef;

#define GPIOA ((GPIO_TypeDef*)GPIO_BASE)""",
        },
        {
            "title": "Chapter 5: GPIO Configuration",
            "text": """General Purpose I/O (GPIO) Configuration Guide

Each GPIO pin can be configured in one of several modes:
- Input (floating, pull-up, pull-down)
- Output (push-pull, open-drain)
- Alternate function (AF0-AF15)
- Analog mode

The GPIO_MODER register controls the mode for each pin:
- 00: Input mode
- 01: Output mode
- 10: Alternate function mode
- 11: Analog mode

Example: Configure PA5 as output (LED):

Step 1: Enable GPIOA clock in RCC
Step 2: Set MODER5[1:0] = 01 (output)
Step 3: Set OTYPER5 = 0 (push-pull)
Step 4: Set OSPEEDR5 = 01 (medium speed)
Step 5: Write to ODR5 to control the LED""",
            "image_pattern": "waveform",
            "code": """// GPIO configuration example
void GPIO_Init(void) {
    // Enable GPIOA clock
    RCC->AHB1ENR |= RCC_AHB1ENR_GPIOAEN;

    // Configure PA5 as output
    GPIOA->MODER &= ~(3 << (5 * 2));  // Clear bits
    GPIOA->MODER |= (1 << (5 * 2));   // Output mode

    // Push-pull output
    GPIOA->OTYPER &= ~(1 << 5);

    // Medium speed
    GPIOA->OSPEEDR &= ~(3 << (5 * 2));
    GPIOA->OSPEEDR |= (1 << (5 * 2));

    // No pull-up/pull-down
    GPIOA->PUPDR &= ~(3 << (5 * 2));
}

void LED_Toggle(void) {
    GPIOA->ODR ^= (1 << 5);
}""",
        },
        {
            "title": "Chapter 6: Timer Configuration",
            "text": """Timer Peripheral Configuration

The device includes multiple general-purpose timers (TIM1-TIM14) with various
features:

Features:
- 16-bit or 32-bit auto-reload counter
- Programmable prescaler
- Multiple independent channels
- PWM generation
- Input capture
- Output compare
- One-pulse mode

Timer Clock Tree:
System Clock → AHB Prescaler → APB1/APB2 Prescaler → Timer Clock

The timer clock frequency depends on the APB prescaler setting:
- If APB prescaler = 1, timer clock = APB clock
- If APB prescaler > 1, timer clock = APB clock × 2

Interrupt Sources:
- Update interrupt (counter overflow/underflow)
- Capture/Compare interrupt
- Trigger interrupt
- Break interrupt (advanced timers)""",
            "image_pattern": "mixed",
            "code": """// Timer configuration for 1kHz PWM
void TIM_PWM_Init(void) {
    // Enable TIM2 clock
    RCC->APB1ENR |= RCC_APB1ENR_TIM2EN;

    // Configure timer for 1kHz @ 84MHz
    // Prescaler: 84 - 1 = 83 (1MHz timer clock)
    // Period: 1000 - 1 = 999 (1kHz PWM)
    TIM2->PSC = 83;
    TIM2->ARR = 999;

    // PWM Mode 1 on Channel 1
    TIM2->CCMR1 |= (6 << 4);  // PWM Mode 1
    TIM2->CCMR1 |= (1 << 3);  // Enable preload

    // Enable output
    TIM2->CCER |= (1 << 0);

    // 50% duty cycle
    TIM2->CCR1 = 500;

    // Start timer
    TIM2->CR1 |= (1 << 0);
}""",
        },
        {
            "title": "Chapter 7: UART Communication",
            "text": """Universal Asynchronous Receiver Transmitter (UART)

The UART peripheral provides serial communication capabilities with the
following features:

Features:
- Configurable baud rate (up to 4.5 Mbps)
- 8 or 9 data bits
- Parity control (even, odd, none)
- Stop bits (1, 1.5, 2)
- Hardware flow control (RTS/CTS)
- DMA support for high-speed transfers

Baud Rate Calculation:
BRR = fPCLK / (16 × BaudRate)

For 115200 baud at 84MHz:
BRR = 84000000 / (16 × 115200) = 45.57 ≈ 45

Interrupt Flags:
- TXE: Transmit data register empty
- RXNE: Receive data register not empty
- TC: Transmission complete
- IDLE: Idle line detected
- ORE: Overrun error
- FE: Framing error""",
            "image_pattern": "grid",
            "code": """// UART initialization
void UART_Init(void) {
    // Enable clocks
    RCC->AHB1ENR |= RCC_AHB1ENR_GPIOAEN;
    RCC->APB1ENR |= RCC_APB1ENR_USART2EN;

    // Configure PA2 (TX) and PA3 (RX) as AF7
    GPIOA->MODER &= ~(0xF << (2 * 2));
    GPIOA->MODER |= (0xA << (2 * 2));  // AF mode
    GPIOA->AFR[0] |= (7 << (2 * 4)) | (7 << (3 * 4));

    // Configure UART: 115200, 8N1
    USART2->BRR = 45;  // 84MHz/115200
    USART2->CR1 = USART_CR1_TE | USART_CR1_RE;
    USART2->CR1 |= USART_CR1_UE;
}

void UART_SendChar(char c) {
    while (!(USART2->SR & USART_SR_TXE));
    USART2->DR = c;
}""",
        },
        {
            "title": "Chapter 8: SPI Interface",
            "text": """Serial Peripheral Interface (SPI)

SPI is a synchronous serial interface used for high-speed communication
with external devices such as:
- Flash memory
- Sensors
- Displays
- SD cards

SPI Modes:
| Mode | CPOL | CPHA | Description           |
|------|------|------|-----------------------|
| 0    | 0    | 0    | Clock idle low        |
| 1    | 0    | 1    | Clock idle low        |
| 2    | 1    | 0    | Clock idle high       |
| 3    | 1    | 1    | Clock idle high       |

Transfer Protocol:
- Master generates clock signal
- Data is shifted on clock edges
- Full duplex: simultaneous TX and RX
- Chip select (NSS) controls slave selection

Maximum SPI clock is typically fPCLK/2.""",
            "image_pattern": "circuit",
            "code": """// SPI Master initialization
void SPI_Init(void) {
    // Enable clocks
    RCC->AHB1ENR |= RCC_AHB1ENR_GPIOAEN;
    RCC->APB2ENR |= RCC_APB2ENR_SPI1EN;

    // Configure SPI pins: PA5=SCK, PA6=MISO, PA7=MOSI
    GPIOA->MODER |= (2 << (5*2)) | (2 << (6*2)) | (2 << (7*2));
    GPIOA->AFR[0] |= (5 << (5*4)) | (5 << (6*4)) | (5 << (7*4));

    // SPI configuration: Master, Mode 0, fPCLK/4
    SPI1->CR1 = SPI_CR1_MSTR | SPI_CR1_BR_0;
    SPI1->CR1 |= SPI_CR1_SPE;
}

uint8_t SPI_Transfer(uint8_t data) {
    SPI1->DR = data;
    while (!(SPI1->SR & SPI_SR_RXNE));
    return SPI1->DR;
}""",
        },
        {
            "title": "Chapter 9: ADC Configuration",
            "text": """Analog-to-Digital Converter (ADC)

The ADC peripheral converts analog signals to digital values.

Features:
- 12-bit resolution (0-4095)
- Multiple input channels (8-16 typically)
- Single, continuous, and scan modes
- DMA support for automatic data transfer
- Analog watchdog for threshold detection

ADC Timing:
- Sampling time: configurable per channel (1.5 to 480 cycles)
- Conversion time: 12 cycles for 12-bit resolution
- Total conversion time = sampling time + conversion time

Voltage Calculation:
V_in = (ADC_Value × V_ref) / 4095

Where V_ref is typically 3.3V.

Channel Assignment:
Channels 0-7 are typically connected to external pins.
Channels 8-15 may include internal signals (temperature sensor, VREFINT).""",
            "image_pattern": "waveform",
            "code": """// ADC initialization and read
void ADC_Init(void) {
    // Enable ADC clock
    RCC->APB2ENR |= RCC_APB2ENR_ADC1EN;

    // Configure ADC
    ADC1->CR1 = 0;
    ADC1->CR2 = ADC_CR2_ADON;  // Enable ADC

    // Set sampling time (56 cycles for channel 0)
    ADC1->SMPR2 = (3 << (0 * 3));

    // Set channel sequence
    ADC1->SQR3 = 0;  // Channel 0 first
}

uint16_t ADC_Read(void) {
    // Start conversion
    ADC1->CR2 |= ADC_CR2_SWSTART;

    // Wait for completion
    while (!(ADC1->SR & ADC_SR_EOC));

    return ADC1->DR;
}

float ADC_ToVoltage(uint16_t value) {
    return (value * 3.3f) / 4095.0f;
}""",
        },
        {
            "title": "Chapter 10: Interrupt Handling",
            "text": """Nested Vector Interrupt Controller (NVIC)

The NVIC manages all exceptions and interrupts in the system.

Interrupt Priority:
- 4-bit priority field (0-15, lower = higher priority)
- Preemption priority: higher priority interrupts can preempt
- Subpriority: determines order when same preemption priority

Interrupt Vectors:
| Vector | Exception       | Priority |
|--------|-----------------|----------|
| 1      | Reset           | -3       |
| 2      | NMI             | -2       |
| 3      | HardFault       | -1       |
| 4-15   | System          | Fixed    |
| 16+    | External IRQ    | Programmable |

Enabling Interrupts:
1. Configure peripheral to generate interrupt
2. Set priority in NVIC
3. Enable IRQ in NVIC ISER register
4. Implement handler function with correct name

Interrupt latency: 12 cycles (typical)""",
            "image_pattern": "diagram",
            "code": """// Interrupt configuration example
void EXTI_Config(void) {
    // Enable SYSCFG clock
    RCC->APB2ENR |= RCC_APB2ENR_SYSCFGEN;

    // Connect PA0 to EXTI0
    SYSCFG->EXTICR[0] &= ~0xF;
    SYSCFG->EXTICR[0] |= 0x0;  // PA0

    // Configure EXTI line 0
    EXTI->IMR |= (1 << 0);     // Enable interrupt
    EXTI->RTSR |= (1 << 0);    // Rising edge trigger

    // Enable NVIC interrupt
    NVIC_SetPriority(EXTI0_IRQn, 0x05);
    NVIC_EnableIRQ(EXTI0_IRQn);
}

// Interrupt handler
void EXTI0_IRQHandler(void) {
    if (EXTI->PR & (1 << 0)) {
        EXTI->PR = (1 << 0);  // Clear pending bit
        // Handle interrupt
    }
}

// Main loop
int main(void) {
    EXTI_Config();
    while(1) { __WFI(); }
}""",
        },
    ]

    for i, content in enumerate(page_contents[:num_pages]):
        page = doc.new_page(width=595, height=842)  # A4 size

        # Add title
        title_rect = fitz.Rect(50, 40, 545, 70)
        page.insert_textbox(title_rect, content["title"], fontsize=18, fontname="helv", color=(0, 0, 0.5))

        # Add horizontal line
        page.draw_line((50, 75), (545, 75), color=(0, 0, 0.5), width=2)

        # Add main text
        text_rect = fitz.Rect(50, 90, 545, 350)
        page.insert_textbox(text_rect, content["text"], fontsize=10, fontname="helv")

        # Add image
        try:
            img_data = create_test_image(400, 200, content["image_pattern"])
            img_rect = fitz.Rect(75, 370, 475, 570)
            page.insert_image(img_rect, stream=img_data)
        except Exception as e:
            # If PIL not available, draw a placeholder
            page.draw_rect(fitz.Rect(75, 370, 475, 570), color=(0.8, 0.8, 0.8))
            page.insert_text((200, 480), f"[Image: {content['image_pattern']}]", fontsize=12)

        # Add code block
        code_rect = fitz.Rect(50, 590, 545, 800)
        page.draw_rect(code_rect, color=(0.9, 0.9, 0.9), fill=(0.97, 0.97, 0.97))
        code_text_rect = fitz.Rect(55, 595, 540, 795)
        page.insert_textbox(code_text_rect, content["code"], fontsize=8, fontname="cour", color=(0.1, 0.1, 0.1))

        # Add page number
        page.insert_text((280, 825), f"Page {i + 1} of {num_pages}", fontsize=9, fontname="helv", color=(0.5, 0.5, 0.5))

    # Save PDF
    doc.save(output_path)
    doc.close()

    return output_path


if __name__ == "__main__":
    output = Path("test_assets/stress_test_10pages.pdf")
    output.parent.mkdir(exist_ok=True)
    create_stress_test_pdf(output, num_pages=10)
    print(f"Created: {output}")
    print(f"Size: {output.stat().st_size / 1024:.1f} KB")
