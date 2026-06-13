## Track: A <br>Team: A7 <br>Project: Digital Compute-in-Memory Macro for Neural Network Matrix Multiplication

Team members
| Discord | Github | Affiliation (experience) | Role |
|---|---|---|---|
| kammy_r | @ratishgupta-guptar76 | McMaster University (undergrad) | Team lead |
| .diable | @alexdiabliu | McMaster University (undergrad) | rtl verification |
| hapler | @hapler | University of Guelpg (post-grad) | rtl verification |
 saeshawadhwa | @wadhwa19 | University of Washington (undergrad) | circuit design |

Overview: This project targets a digital compute-in-memory (DCIM) macro for parameterized fixed-point dot-product acceleration on GF180MCU, designed for the open-source LibreLane RTL-to-GDS flow. Weights are held stationary in a custom 8T SRAM bitcell array; multiplication occurs locally at the cell, and partial sums are reduced through column-level digital adder trees, eliminating the data-movement cost of conventional MAC arrays.

Size: 500um x 100um (estimate) or block type (see padring proposal below)
Required pins: 6

> See the [padring proposal](https://docs.google.com/presentation/d/1Xv_e0r1JKkjAIttDKGDsLEcDNz211jee_gQeWR6n7Es/edit?usp=sharing) for block sizes and pin counts.

Links
[Github repo](https://github.com/wafer-space/gf180mcu-project-template):

[Proposal Slide Link](https://github.com/sscs-ose/sscs-chipathon-2026/blob/main/resources/documents/template_2026_ChipathonProposals.pptx)

[Pin Requirement Link](https://docs.google.com/spreadsheets/d/1pHG3cbpYbGc9qAq9G-NZkLor6GjWBoljDVpwNgFM__g/edit?usp=sharing)

[Progress tracker]()

[Schematic Review Slide Link]()

[Layout Review Slide Link]()