
En magisk jukeboks der kører på raspberry pi.

Til at begynde med skal vi kun have styr på web servicen og state machinen. Lav kun placeholder for de andre og glem at det er en raspberry pi for nu, Skal kunne teste den på min pc.



# Hardware
## Raspberry pi 4
## Speaker and amplifier
### AMP XH-M567 TPA3116D2 
## Op til 4 arcade knapper til musik quiz
## 4 knapper til navigation

### Tingd der skal installeres på pi'en
tailscale for remote access
Noget for bluetooth management


# Web service Kører på flask og python
## Backend
### Her skal alt debugging, logging og status på alle programmerne være.
### Her skal man også kunne skifte mellem forskellige modes og afspille forskellige forlavede lokale mp3 eller wav filer.
### Man skal også kunne force næste trin i en state, f.eks. hvis den afventer et tryk på en knap, skal man kunne trykke på den fra backenden, for at give dem illusionen af at det fungerer
## Front end
### En simpel hjemmeside hvor man kan se batteriniveu, internet forbindelse og hvilken mode den er I, om den lytter på mikrofonen, forventer input eller om den venter
### Man skal også kunne læse beskeder fra backenden



# State machine
## Holder styr på hvilken mode jukeboksen er i
## Skal kunne køres async

# Mode_Bluetooth speaker
## Skal fungere som en simpel bluetooth højtaler hvor ens smartphone parres med jukeboksen, den skal glemme alle paringer hver gang, så den nemt kan forbindes til en ny telefon.

# Mode_Aktivitet_N
## der skal være forskellige modes til forskellige aktiviter, der endnu ikke er helt forklaret.

# Musik quiz mode
## Ligesom bluetooth mode forbindes en smartphone som input via bluetooth
## Aflæs og afvent kna


# Afvent opgadering mode
##
