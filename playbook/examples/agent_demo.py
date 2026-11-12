"""Call the three VLOnto tools the way an agent tool server would."""
from vlonto_tools import VLOntoTools, to_text

kg = VLOntoTools("kg")
print(to_text(kg.check_validity("10/2012/QH13")))
print()
print(to_text(kg.expand_citations("45/2019/QH14", "35")))
print()
print(to_text(kg.related_provisions("45/2019/QH14", "169")))
