; Dominio STRIPS del rover, conferencia C2b, seccion 2.
; Hechos: (en ?x) exactamente uno por estado (invariante, mutex entre
; lugares); (muestra-en ?m ?x), (tiene ?m), (analizada ?m),
; (transmitida ?m) exactamente un estadio por muestra; (zona-com ?x)
; y (conectado ?x ?y) son estaticos. La bateria y la memoria no son
; hechos STRIPS: se tratan como recursos numericos fuera del dominio
; (C2b, seccion 6, opcion 2: el planificador decide la secuencia y la
; capa de recursos inserta recargas/transmisiones por memoria llena).
; Bajar una loma no gasta bateria: el coste del paso es 0 si dz < 0,
; y en este dominio clasico sin costes cada accion cuesta 1, salvo
; que se use :action-costs con el coste de terreno (ver AGENTE.md).
(define (domain rover)
  (:requirements :strips :typing)
  (:types lugar muestra)
  (:predicates
    (en ?x - lugar)
    (conectado ?x ?y - lugar)
    (muestra-en ?m - muestra ?x - lugar)
    (tiene ?m - muestra)
    (analizada ?m - muestra)
    (transmitida ?m - muestra)
    (zona-com ?x - lugar))
  (:action mover
    :parameters (?desde ?hasta - lugar)
    :precondition (and (en ?desde) (conectado ?desde ?hasta))
    :effect (and (en ?hasta) (not (en ?desde))))
  (:action recolectar
    :parameters (?m - muestra ?x - lugar)
    :precondition (and (en ?x) (muestra-en ?m ?x))
    :effect (and (tiene ?m) (not (muestra-en ?m ?x))))
  (:action analizar
    :parameters (?m - muestra)
    :precondition (tiene ?m)
    :effect (analizada ?m))
  (:action transmitir
    :parameters (?m - muestra ?x - lugar)
    :precondition (and (analizada ?m) (en ?x) (zona-com ?x))
    :effect (transmitida ?m))
  (:action recargar
    :parameters (?x - lugar)
    :precondition (and (en ?x) (zona-com ?x))
    :effect (and)))
