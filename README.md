# Arno

![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)

**Arno** (Adjustable Resource-NAND Orchestrator) is a scalable SSD simulator implemented in Python 3.11.  
It allows performance and latency analysis based on customizable NAND configurations and supports simulation under various I/O traces and workload scenarios.  
Additionally, Arno provides QoS evaluation capabilities, making it suitable for studying real-world SSD behavior under different conditions.

---

## Features

- **Performance Metrics**: Measure read/write throughput and latency
- **Workload Patterns**: Supports sequential and random read/write
- **Customizable Configuration**: Easily change number of channels, ways, and planes
- **Predefined Workload**:
  - `performance`: Includes 4 basic scenarios (sequential/random read/write)

---

## Requirements

- **Python 3.11**
- Required packages are listed in `requirements.txt`

---


## How to Run

To execute the simulator:

```bash
python storage_simulator.py --pre-defined-workload performance
```

To view available options:

```bash
python storage_simulator.py --help
```

---

## Configuration Options

| Argument                      | Type  | Default         | Description                                                               |
|-------------------------------|-------|-----------------|---------------------------------------------------------------------------|
| `--pcie-gen`                  | int   | `5`             | PCIe generation number. Choose from {4, 5, 6}                             |
| `--channel`                   | int   | `16`            | Number of NAND channels                                                   |
| `--way`                       | int   | `2`             | Number of ways per channel                                                |
| `--plane`                     | int   | `4`             | Number of planes per die                                                  |
| `--nand-io-mbps`              | int   | `0`             | NAND interface bandwidth in Mbps                                          |
| `--nand-product`              | str   | `'TLC_EXAMPLE'` | NAND model (more types to be supported later)                             |
| `--nand-cell-type`            | str   | `TLC`           | NAND type (Supports SLC, MLC, TLC)                                        |
| `--gc-threshold`              | float | `0.2`           | The threshold ratio for triggering GC                                     |
| `--urgent-gc-threshold`       | float | `0.05`          | The threshold ratio for triggering urgent GC (Urgent GC halts host write) |
| `--sustained-block-rate`      | float | `0.8`           | Ratio of blocks to fill under sustained conditions                        |
| `--sustained-page-rate`       | float | `0.8`           | Ratio of pages to fill under sustained conditions                         |
| `--make-sustained`            | flag  | `True`          | Make NAND into sustained state                                            |
| `--workload-type`             | str   | `'basic'`       | Workload type option ('pcmark10' is only supported.)                      |
| `--pre-defined-workload`      | str   | None            | Select a predefined workload scenario                                     |
| `--range-bytes`               | str   | None            | Total data range (Bytes) of each TestCase                                 |
| `--folder-name`               | str   | None            | Name of the output folder for results                                     |
| `--enable-command-record`     | flag  | `False`         | Enable recording of command traces                                        |
| `--enable-performance-record` | flag  | `False`         | Enable recording of performance logs                                      |
| `--enable-utilization`        | flag  | `False`         | Enable recording of resource utilization                                  |
## Example

```bash

# Use a pre-defined workload (any --range-bytes will be ignored)
python storage_simulator.py --pre-defined-workload performance_256MB

# Use the default workload 'performance' with a custom size
python storage_simulator.py --range-bytes 512MB

# Run with all defaults (default workload 'performance' and its default size)
python storage_simulator.py

# Run with pcmark10 I/O trace
python storage_simulator.py --workload-type pcmark10

# Other example
python storage_simulator.py --pre-defined-workload performance_512MB \\  
  --pcie-gen 5 \\
  --channel 16 --way 2 --plane 4 \\
  --nand-product TLC_EXAMPLE \\
  --enable-performance-record --folder-name results/test
```

---

## Output

- Average latency
- Total number of I/O operations
- Throughput (MB/s)
- Latency distribution and statistics

---

## Project Structure

```text
Arno/
├── core/                   # Core logic and behavior (NAND, Buffer, Bus, etc.)
├── product/general/        # SSD-level functionality implementation
├── output/                 # Stores simulation results
├── storage_simulator.py    # Main entry point for simulation
├── requirements.txt
└── README.md

```

## License
This project is distributed under the terms of the MIT License (see LICENSE).

It also includes third-party libraries that are subject to their own license terms.
For details, please refer to THIRD_PARTY_LICENSES.