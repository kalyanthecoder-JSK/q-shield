
"""
Q-SHIELD: BB84 Quantum Key Distribution Simulator
Educational simulation only — not real quantum hardware.
"""

import random


def random_bits(n, rng):
    """Generate n random classical bits."""
    return [rng.randint(0, 1) for _ in range(n)]


def measure_qubit(bit, preparation_basis, measurement_basis, rng):
    """
    Simulate a BB84 measurement.

    Basis 0 = rectilinear (Z): |0>, |1>
    Basis 1 = diagonal (X):   |+>, |->

    Same basis: result is the prepared bit.
    Different basis: result is random with equal probability.
    """
    if preparation_basis == measurement_basis:
        return bit
    return rng.randint(0, 1)


def simulate_bb84(
    n_bits=1000,
    eve_present=False,
    sample_fraction=0.20,
    qber_threshold=0.11,
    seed=None,
):

    """Simulate BB84, estimate QBER, and decide whether to accept the run."""

    if n_bits < 10:
        raise ValueError("Use at least 10 transmitted bits.")
    if not 0 < sample_fraction < 1:
        raise ValueError("sample_fraction must be between 0 and 1.")
    if not 0 <= qber_threshold <= 1:
        raise ValueError("qber_threshold must be between 0 and 1.")

    rng = random.Random(seed)

    # Step 1: Alice generates random bits and preparation bases.
    alice_bits = random_bits(n_bits, rng)
    alice_bases = random_bits(n_bits, rng)

    # Step 2: Eve may intercept, measure, and resend each state.
    transmitted_bits = []
    transmitted_bases = []

    if eve_present:
        eve_bases = random_bits(n_bits, rng)

        for i in range(n_bits):
            eve_result = measure_qubit(
                alice_bits[i], alice_bases[i], eve_bases[i], rng
            )
            # Eve resends a state prepared in the basis she measured.
            transmitted_bits.append(eve_result)
            transmitted_bases.append(eve_bases[i])
    else:
        transmitted_bits = alice_bits[:]
        transmitted_bases = alice_bases[:]

    # Step 3: Bob chooses random bases and measures.
    bob_bases = random_bits(n_bits, rng)
    bob_bits = [
        measure_qubit(
            transmitted_bits[i],
            transmitted_bases[i],
            bob_bases[i],
            rng,
        )
        for i in range(n_bits)
    ]

    # Step 4: Alice and Bob publicly compare bases, not bit values.
    sifted_positions = [
        i for i in range(n_bits)
        if alice_bases[i] == bob_bases[i]
    ]

    alice_sifted = [alice_bits[i] for i in sifted_positions]
    bob_sifted = [bob_bits[i] for i in sifted_positions]

    # Step 5: Reveal a random sample to estimate the error rate.
    sample_count = max(1, int(len(sifted_positions) * sample_fraction))
    sample_count = min(sample_count, len(sifted_positions))

    sample_indices = list(range(len(sifted_positions)))
    rng.shuffle(sample_indices)
    sample_indices = set(sample_indices[:sample_count])

    errors = sum(
        alice_sifted[i] != bob_sifted[i]
        for i in sample_indices
    )
    qber = errors / sample_count if sample_count else 1.0

    # Sample bits are disclosed and must not be used as key bits.
    remaining_indices = [
        i for i in range(len(sifted_positions))
        if i not in sample_indices
    ]
    alice_candidate = [alice_sifted[i] for i in remaining_indices]
    bob_candidate = [bob_sifted[i] for i in remaining_indices]

    accepted = (
        len(sifted_positions) > 0
        and sample_count >= 1
        and qber <= qber_threshold
    )

    # Do not present a candidate as a secure final key.
    # Error correction and privacy amplification are not implemented.
    return {
        "transmitted_bits": n_bits,
        "sifted_bits": len(sifted_positions),
        "sample_bits": sample_count,
        "sample_errors": errors,
        "qber": qber,
        "eve_present": eve_present,
        "accepted": accepted,
        "alice_candidate": "".join(map(str, alice_candidate)),
        "bob_candidate": "".join(map(str, bob_candidate)),
        "candidate_bits_match": alice_candidate == bob_candidate,
        "final_secure_key_generated": False,
    }


def main():
    print("=" * 54)
    print("       Q-SHIELD | BB84 SIMULATION")
    print("=" * 54)
    print("1. Normal communication (no Eve)")
    print("2. Simulate intercept-and-resend Eve")

    choice = input("Select scenario (1 or 2): ").strip()
    if choice not in {"1", "2"}:
        print("Invalid choice. Please select 1 or 2.")
        return

    try:
        n_bits = int(input("Number of transmitted bits [1000]: ") or "1000")
        result = simulate_bb84(
            n_bits=n_bits,
            eve_present=(choice == "2"),
        )
    except ValueError as exc:
        print(f"Input error: {exc}")
        return

    print("\n--- Simulation Results ---")
    print(f"Transmitted bits : {result['transmitted_bits']}")
    print(f"Sifted bits      : {result['sifted_bits']}")
    print(f"Sample bits      : {result['sample_bits']}")
    print(f"Sample errors    : {result['sample_errors']}")
    print(f"Estimated QBER   : {result['qber']:.2%}")
    print(f"Eve simulated    : {'Yes' if result['eve_present'] else 'No'}")
    print(f"Key check        : {'PASS' if result['accepted'] else 'ABORT'}")

    print("\n--- Security Interpretation ---")
    if result["accepted"]:
        print("The sample QBER is within the configured threshold.")
        print("This alone does NOT prove the link is secure.")
    else:
        print("Reject this run's candidate key and raise an alert.")

    print("\nCandidate key bits:", len(result["alice_candidate"]))
    print("Candidate keys match:", result["candidate_bits_match"])
    print("Final secure key generated: NO")
    print("Reason: error correction and privacy amplification")
    print("are not implemented in this educational prototype.")


if __name__ == "__main__":
    main()
